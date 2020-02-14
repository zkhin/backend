import pytest

from app.models.media.enums import MediaSize, MediaStatus


@pytest.fixture
def user(user_manager):
    yield user_manager.create_cognito_only_user('uid', 'uname')


@pytest.fixture
def album(album_manager, user):
    yield album_manager.add_album(user.id, 'aid', 'album name')


@pytest.fixture
def completed_image_post(post_manager, user):
    post = post_manager.add_post(user.id, 'pid1', media_uploads=[{'mediaId': 'mid1'}])
    media = post_manager.media_manager.init_media(post.item['mediaObjects'][0])
    for size in MediaSize._ALL:
        path = media.get_s3_path(size)
        post_manager.clients['s3_uploads'].put_object(path, b'anything', 'application/octet-stream')
    media.set_status(MediaStatus.UPLOADED)
    media.set_checksum()
    post.complete()
    yield post


@pytest.fixture
def text_only_post(post_manager, user):
    yield post_manager.add_post(user.id, 'pid1', text='t')


def test_serialize(user, album):
    resp = album.serialize('caller-uid')
    assert resp.pop('ownedBy')['userId'] == user.id
    assert resp == album.item


def test_update(album):
    # check starting state
    assert album.item['name'] == 'album name'
    assert 'description' not in album.item

    # edit both
    album.update(name='new name', description='new desc')
    assert album.item['name'] == 'new name'
    assert album.item['description'] == 'new desc'

    # remove the description
    album.update(description='')
    assert album.item['name'] == 'new name'
    assert 'description' not in album.item

    # check can't delete name
    with pytest.raises(album.exceptions.AlbumException):
        album.update(name='')


def test_delete_no_posts(user, album):
    # verify the album really exists, and the user's albumCount
    user.refresh_item()
    assert user.item.get('albumCount', 0) == 1
    album.refresh_item()
    assert album.item

    album.delete()

    # verify the album has been deleted
    user.refresh_item()
    assert user.item.get('albumCount', 0) == 0
    album.refresh_item()
    assert album.item is None


def test_delete(user, album, post_manager):
    # create two posts in the album
    post1 = post_manager.add_post(user.id, 'pid1', media_uploads=[{'mediaId': 'mid1'}], album_id=album.id)
    media1 = post_manager.media_manager.init_media(post1.item['mediaObjects'][0])
    post2 = post_manager.add_post(user.id, 'pid2', media_uploads=[{'mediaId': 'mid2'}], album_id=album.id)
    media2 = post_manager.media_manager.init_media(post2.item['mediaObjects'][0])

    # to look like a COMPLETED media post during the restore process,
    # we need to put objects in the mock s3 for all image sizes
    for size in MediaSize._ALL:
        media1_path = media1.get_s3_path(size)
        media2_path = media2.get_s3_path(size)
        post_manager.clients['s3_uploads'].put_object(media1_path, b'anything', 'application/octet-stream')
        post_manager.clients['s3_uploads'].put_object(media2_path, b'anything', 'application/octet-stream')
    media1.set_status(MediaStatus.UPLOADED)
    media1.set_checksum()
    media2.set_status(MediaStatus.UPLOADED)
    media2.set_checksum()

    # complete the posts
    post1.complete()
    post2.complete()

    # verify starting state: can see album, posts are in it, user's albumCount, album art exists
    assert post1.item['albumId'] == album.id
    assert post2.item['albumId'] == album.id
    user.refresh_item()
    assert user.item.get('postCount', 0) == 2
    assert user.item.get('albumCount', 0) == 1
    album.refresh_item()
    for size in MediaSize._ALL:
        path = album.get_art_image_path(size)
        assert album.s3_uploads_client.exists(path)

    # delete the album
    album.delete()

    # verify new state: cannot see album, posts are *not* in it, user's albumCount, album art exists
    post1.refresh_item()
    assert 'albumId' not in post1.item
    post2.refresh_item()
    assert 'albumId' not in post2.item
    user.refresh_item()
    assert user.item.get('postCount', 0) == 2
    assert user.item.get('albumCount', 0) == 0
    for size in MediaSize._ALL:
        path = album.get_art_image_path(size)
        assert not album.s3_uploads_client.exists(path)


def test_delete_cant_decrement_album_count_below_zero(user, album):
    # sneak behind the model and decrement the user's albumCount, verify
    transact = user.dynamo.transact_decrement_album_count(user.id)
    user.dynamo.client.transact_write_items([transact])
    user.refresh_item()
    assert user.item.get('albumCount', 0) == 0

    # verify deletion fails
    with pytest.raises(album.exceptions.AlbumException):
        album.delete()

    # verify album still exists
    album.refresh_item()
    assert album.item


def test_get_art_image_path(album):
    # test when album has no art
    assert 'artHash' not in album.item
    for size in MediaSize._ALL:
        assert album.get_art_image_path(size) is None

    # set an artHash, in mem is enough
    album.item['artHash'] = 'deadbeef'
    for size in MediaSize._ALL:
        path = album.get_art_image_path(size)
        assert album.item['ownedByUserId'] in path
        assert 'album' in path
        assert album.id in path
        assert album.item['artHash'] in path
        assert size in path


def test_get_art_image_url(album):
    image_url = 'https://the-image.com'
    album.cloudfront_client.configure_mock(**{
        'generate_presigned_url.return_value': image_url,
    })

    # should get placeholder image when album has no artHash
    assert 'artHash' not in album.item
    domain = 'here.there.com'
    album.frontend_resources_domain = domain
    for size in MediaSize._ALL:
        url = album.get_art_image_url(size)
        assert domain in url
        assert size in url

    # set an artHash, in mem is enough
    album.item['artHash'] = 'deadbeef'
    url = album.get_art_image_url(MediaSize.NATIVE)
    for size in MediaSize._ALL:
        assert album.get_art_image_url(size) == image_url


def test_delete_art_images(album):
    # set an art hash and put imagery in mocked s3
    art_hash = 'hashing'
    for size in MediaSize._ALL:
        media1_path = album.get_art_image_path(size, art_hash)
        album.s3_uploads_client.put_object(media1_path, b'anything', 'application/octet-stream')

    # verify we can see that album art
    for size in MediaSize._ALL:
        path = album.get_art_image_path(size, art_hash)
        assert album.s3_uploads_client.exists(path)

    # delete the art
    album.delete_art_images(art_hash)

    # verify we cannot see that album art anymore
    for size in MediaSize._ALL:
        path = album.get_art_image_path(size, art_hash)
        assert not album.s3_uploads_client.exists(path)


def test_update_art_images_one_post(album, completed_image_post, post_manager, media_manager, s3_client):
    post = completed_image_post
    media_item = next(media_manager.dynamo.generate_by_post(post.id, uploaded=True), None)
    media = media_manager.init_media(media_item)

    # check no no art for album
    assert 'artHash' not in album.item
    for size in MediaSize._ALL:
        assert album.get_art_image_path(size) is None

    # update the album art with that post
    art_hash = 'the-hash'
    album.update_art_images_one_post(art_hash, post.id)

    # check art was updated correctly
    for size in MediaSize._ALL:
        art_path = album.get_art_image_path(size, art_hash=art_hash)
        assert art_hash in art_path
        # verify art matches the post's media
        art_data = s3_client.get_object_data_stream(art_path).read()
        image_path = media.get_s3_path(size)
        image_data = s3_client.get_object_data_stream(image_path).read()
        assert art_data == image_data


def test_cannot_update_album_art_with_text_only_post(album, text_only_post):
    # update the album art with that post
    art_hash = 'the hash'
    with pytest.raises(Exception) as err:
        album.update_art_images_one_post(art_hash, text_only_post.id)
    assert 'uploaded media' in str(err)
