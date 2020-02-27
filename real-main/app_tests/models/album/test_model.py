from io import BytesIO
from os import path
from unittest.mock import Mock

import pytest

from app.models.post.enums import PostType
from app.utils import image_size

grant_horz_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'grant-horizontal.jpg')
grant_vert_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'grant-vertical.jpg')


@pytest.fixture
def user(user_manager):
    yield user_manager.create_cognito_only_user('uid', 'uname')


@pytest.fixture
def album(album_manager, user):
    yield album_manager.add_album(user.id, 'aid', 'album name')


@pytest.fixture
def completed_image_post(post_manager, user, image_data_b64, mock_post_verification_api):
    yield post_manager.add_post(user.id, 'pid1', media_uploads=[{'mediaId': 'mid1', 'imageData': image_data_b64}])


@pytest.fixture
def text_only_post(post_manager, user):
    yield post_manager.add_post(user.id, 'pid1', PostType.TEXT_ONLY, text='t')


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


def test_delete(user, album, post_manager, image_data_b64, mock_post_verification_api):
    # create two posts in the album
    post1 = post_manager.add_post(
        user.id, 'pid1', PostType.IMAGE, media_uploads=[{'mediaId': 'mid1', 'imageData': image_data_b64}],
        album_id=album.id,
    )
    post2 = post_manager.add_post(
        user.id, 'pid2', PostType.IMAGE, media_uploads=[{'mediaId': 'mid2', 'imageData': image_data_b64}],
        album_id=album.id,
    )

    # verify starting state: can see album, posts are in it, user's albumCount, album art exists
    assert post1.item['albumId'] == album.id
    assert post2.item['albumId'] == album.id
    user.refresh_item()
    assert user.item.get('postCount', 0) == 2
    assert user.item.get('albumCount', 0) == 1
    album.refresh_item()
    for size in image_size.ALL:
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
    for size in image_size.ALL:
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
    for size in image_size.ALL:
        assert album.get_art_image_path(size) is None

    # set an artHash, in mem is enough
    album.item['artHash'] = 'deadbeef'
    for size in image_size.ALL:
        path = album.get_art_image_path(size)
        assert album.item['ownedByUserId'] in path
        assert 'album' in path
        assert album.id in path
        assert album.item['artHash'] in path
        assert size.name in path


def test_get_art_image_url(album):
    image_url = 'https://the-image.com'
    album.cloudfront_client.configure_mock(**{
        'generate_presigned_url.return_value': image_url,
    })

    # should get placeholder image when album has no artHash
    assert 'artHash' not in album.item
    domain = 'here.there.com'
    album.frontend_resources_domain = domain
    for size in image_size.ALL:
        url = album.get_art_image_url(size)
        assert domain in url
        assert size.name in url

    # set an artHash, in mem is enough
    album.item['artHash'] = 'deadbeef'
    url = album.get_art_image_url(image_size.NATIVE)
    for size in image_size.ALL:
        assert album.get_art_image_url(size) == image_url


def test_delete_art_images(album):
    # set an art hash and put imagery in mocked s3
    art_hash = 'hashing'
    for size in image_size.ALL:
        media1_path = album.get_art_image_path(size, art_hash)
        album.s3_uploads_client.put_object(media1_path, b'anything', 'application/octet-stream')

    # verify we can see that album art
    for size in image_size.ALL:
        path = album.get_art_image_path(size, art_hash)
        assert album.s3_uploads_client.exists(path)

    # delete the art
    album.delete_art_images(art_hash)

    # verify we cannot see that album art anymore
    for size in image_size.ALL:
        path = album.get_art_image_path(size, art_hash)
        assert not album.s3_uploads_client.exists(path)


def test_save_art_images(album):
    assert 'artHash' not in album.item
    art_hash = 'the hash'

    # check nothing in S3
    for size in image_size.ALL:
        path = album.get_art_image_path(size, art_hash)
        assert not album.s3_uploads_client.exists(path)

    # save an image as the art
    with open(grant_horz_path, 'rb') as fh:
        image_data = fh.read()
    album.save_art_images(art_hash, BytesIO(image_data))

    # check all sizes are in S3
    for size in image_size.ALL:
        path = album.get_art_image_path(size, art_hash)
        assert album.s3_uploads_client.exists(path)

    # check the value of the native image
    native_path = album.get_art_image_path(image_size.NATIVE, art_hash)
    assert album.s3_uploads_client.get_object_data_stream(native_path).read() == image_data

    # save an new image as the art
    with open(grant_vert_path, 'rb') as fh:
        image_data = fh.read()
    album.save_art_images(art_hash, BytesIO(image_data))

    # check all sizes are in S3
    for size in image_size.ALL:
        path = album.get_art_image_path(size, art_hash)
        assert album.s3_uploads_client.exists(path)

    # check the value of the native image
    native_path = album.get_art_image_path(image_size.NATIVE, art_hash)
    assert album.s3_uploads_client.get_object_data_stream(native_path).read() == image_data


def test_rank_count(album):
    assert 'rank' not in album.item
    assert album.get_next_first_rank() == 0
    assert album.get_next_last_rank() == 0

    album.item['rankCount'] = 0
    assert album.get_next_first_rank() == 0
    assert album.get_next_last_rank() == 0

    album.item['rankCount'] = 1
    assert album.get_next_first_rank() == pytest.approx(-1 / 3)
    assert album.get_next_last_rank() == pytest.approx(1 / 3)

    album.item['rankCount'] = 2
    assert album.get_next_first_rank() == pytest.approx(-2 / 4)
    assert album.get_next_last_rank() == pytest.approx(2 / 4)

    album.item['rankCount'] = 3
    assert album.get_next_first_rank() == pytest.approx(-3 / 5)
    assert album.get_next_last_rank() == pytest.approx(3 / 5)

    album.item['rankCount'] = 4
    assert album.get_next_first_rank() == pytest.approx(-4 / 6)
    assert album.get_next_last_rank() == pytest.approx(4 / 6)

    album.item['rankCount'] = 5
    assert album.get_next_first_rank() == pytest.approx(-5 / 7)
    assert album.get_next_last_rank() == pytest.approx(5 / 7)


def test_get_post_ids_for_art(album):
    album.post_manager.dynamo.generate_post_ids_in_album = Mock()

    # no post ids
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = []
    assert album.get_post_ids_for_art() == []

    # one post ids
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = list(range(1))
    assert album.get_post_ids_for_art() == [0]

    # three post ids
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = list(range(3))
    assert album.get_post_ids_for_art() == [0]

    # four post ids
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = list(range(4))
    assert album.get_post_ids_for_art() == [0, 1, 2, 3]

    # eigth post ids
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = list(range(8))
    assert album.get_post_ids_for_art() == [0, 1, 2, 3]

    # nine post ids
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = list(range(9))
    assert album.get_post_ids_for_art() == [0, 1, 2, 3, 4, 5, 6, 7, 8]

    # 15 post ids
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = list(range(15))
    assert album.get_post_ids_for_art() == [0, 1, 2, 3, 4, 5, 6, 7, 8]

    # 16 post ids
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = list(range(16))
    assert album.get_post_ids_for_art() == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
