import pytest


@pytest.fixture
def user(user_manager):
    yield user_manager.create_cognito_only_user('uid', 'uname')


@pytest.fixture
def album(album_manager, user):
    yield album_manager.add_album(user.id, 'aid', 'album name')


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
    post1 = post_manager.add_post(user.id, 'pid1', text='lore', album_id=album.id)
    post2 = post_manager.add_post(user.id, 'pid2', text='ipsum', album_id=album.id)

    # verify starting state: can see album, posts are in it, user's albumCount
    assert post1.item['albumId'] == album.id
    assert post2.item['albumId'] == album.id
    user.refresh_item()
    assert user.item.get('postCount', 0) == 2
    assert user.item.get('albumCount', 0) == 1

    # delete the album
    album.delete()

    # verify new state: cannot see album, posts are *not* in it, user's albumCount
    post1.refresh_item()
    assert 'albumId' not in post1.item
    post2.refresh_item()
    assert 'albumId' not in post2.item
    user.refresh_item()
    assert user.item.get('postCount', 0) == 2
    assert user.item.get('albumCount', 0) == 0


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
