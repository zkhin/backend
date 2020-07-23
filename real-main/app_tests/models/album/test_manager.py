from uuid import uuid4

import pendulum
import pytest

from app.models.album.exceptions import AlbumException
from app.models.post.enums import PostType
from app.utils import image_size


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def album(album_manager, user):
    yield album_manager.add_album(user.id, str(uuid4()), 'album name')


def test_add_album_minimal(album_manager, user):
    album_id = 'aid'

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


def test_add_album_empty_string_description(album_manager, user):
    # add the album
    album_id = 'aid'
    album = album_manager.add_album(user.id, album_id, 'album name', description='')

    # verify the album looks correct
    assert album.id == album_id
    assert 'description' not in album.item


def test_add_album_maximal(album_manager, user):
    album_id = 'aid'

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


def test_add_album_errors(album_manager, user):
    album_id = 'aid'

    # already used the album_id
    album_manager.add_album(user.id, album_id, 'album name')
    with pytest.raises(AlbumException):
        album_manager.add_album(user.id, album_id, 'album name')


def test_delete_all_by_user(album_manager, user):
    # delete all for a user that has none, verify no error
    album_manager.delete_all_by_user('uid-none')

    # add two albums for our user
    album_id_1, album_id_2 = 'aid1', 'aid2'
    album_manager.add_album(user.id, album_id_1, 'album name')
    album_manager.add_album(user.id, album_id_2, 'album name')

    # verify we can see those albums
    album_items = list(album_manager.dynamo.generate_by_user(user.id))
    assert len(album_items) == 2
    assert album_items[0]['albumId'] == album_id_1
    assert album_items[1]['albumId'] == album_id_2

    # delete them all, verify
    album_manager.delete_all_by_user(user.id)
    assert list(album_manager.dynamo.generate_by_user(user.id)) == []


def test_on_album_delete_delete_album_art(album_manager, post_manager, user, album, image_data_b64):
    # fire for a delete of an album with no art, verify no error
    assert 'artHash' not in album.item
    album_manager.on_album_delete_delete_album_art(album.id, old_item=album.item)

    # add a post with an image to the album to get some art in S3, verify
    post_manager.add_post(
        user, str(uuid4()), PostType.IMAGE, image_input={'imageData': image_data_b64}, album_id=album.id
    )
    assert 'artHash' in album.refresh_item().item
    art_paths = [album.get_art_image_path(size) for size in image_size.JPEGS]
    for path in art_paths:
        assert album.s3_uploads_client.exists(path) is True

    # fire for delete of that ablum with art, verify art is deleted from S3
    album_manager.on_album_delete_delete_album_art(album.id, old_item=album.item)
    for path in art_paths:
        assert album.s3_uploads_client.exists(path) is False
