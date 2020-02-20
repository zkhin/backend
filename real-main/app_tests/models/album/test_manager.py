import pendulum
import pytest


@pytest.fixture
def user(user_manager):
    yield user_manager.create_cognito_only_user('uid', 'uname')


def test_add_album_minimal(album_manager, user):
    album_id = 'aid'

    # verify the user has no albums
    assert user.item.get('albumCount', 0) == 0

    # add the album
    before = pendulum.now('utc')
    album = album_manager.add_album(user.id, album_id, 'album name')
    after = pendulum.now('utc')

    # verify the album looks correct
    assert album.id == album_id
    assert album.item['ownedByUserId'] == user.id
    assert album.item['name'] == 'album name'
    assert 'description' not in album.item
    assert album.item['createdAt'] >= before.to_iso8601_string()
    assert album.item['createdAt'] <= after.to_iso8601_string()
    assert album.item.get('postCount', 0) == 0
    assert 'postsLastUpdatedAt' not in album.item

    # verify the count incremented on the user object
    user.refresh_item()
    assert user.item.get('albumCount', 0) == 1


def test_add_album_empty_string_description(album_manager, user):
    # add the album
    album_id = 'aid'
    album = album_manager.add_album(user.id, album_id, 'album name', description='')

    # verify the album looks correct
    assert album.id == album_id
    assert 'description' not in album.item


def test_add_album_maximal(album_manager, user):
    album_id = 'aid'

    # verify the user has no albums
    assert user.item.get('albumCount', 0) == 0

    # add the album
    now = pendulum.now('utc')
    album = album_manager.add_album(user.id, album_id, 'album name', description='a desc', now=now)

    # verify the album looks correct
    assert album.id == album_id
    assert album.item['ownedByUserId'] == user.id
    assert album.item['name'] == 'album name'
    assert album.item['description'] == 'a desc'
    assert album.item['createdAt'] == now.to_iso8601_string()
    assert album.item.get('postCount', 0) == 0
    assert 'postsLastUpdatedAt' not in album.item

    # verify the count incremented on the user object
    user.refresh_item()
    assert user.item.get('albumCount', 0) == 1


def test_add_album_errors(album_manager, user):
    album_id = 'aid'

    # user doesn't exist
    with pytest.raises(album_manager.exceptions.AlbumException):
        album_manager.add_album('uid-dne', album_id, 'album name')

    # already used the album_id
    album_manager.add_album(user.id, album_id, 'album name')
    with pytest.raises(album_manager.exceptions.AlbumException):
        album_manager.add_album(user.id, album_id, 'album name')


def test_delete_all_by_user(album_manager, user):
    # delete all for a user that has none, verify no error
    album_manager.delete_all_by_user('uid-none')

    # add two albums for our user
    album_id_1, album_id_2 = 'aid1', 'aid2'
    album_manager.add_album(user.id, album_id_1, 'album name')
    album_manager.add_album(user.id, album_id_2, 'album name')

    # verify we can see those albums and our count of them
    album_items = list(album_manager.dynamo.generate_by_user(user.id))
    assert len(album_items) == 2
    assert album_items[0]['albumId'] == album_id_1
    assert album_items[1]['albumId'] == album_id_2
    user.refresh_item()
    assert user.item.get('albumCount', 0) == 2

    # delete them all
    album_manager.delete_all_by_user(user.id)

    # verify they're gone and our count decremented
    assert list(album_manager.dynamo.generate_by_user(user.id)) == []
    user.refresh_item()
    assert user.item.get('albumCount', 0) == 0
