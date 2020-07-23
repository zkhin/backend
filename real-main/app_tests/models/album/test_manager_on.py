from unittest.mock import patch
from uuid import uuid4

import pytest

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


def test_on_album_add_edit_sync_delete_at(album_manager, user, album):
    assert 'gsiK1PartitionKey' not in album.item
    assert 'gsiK1SortKey' not in album.item

    # fire for newly created album, verify state
    album_manager.on_album_add_edit_sync_delete_at(album.id, new_item=album.item)
    album.refresh_item()
    assert 'gsiK1PartitionKey' in album.item
    assert 'gsiK1SortKey' in album.item

    # fire for a post added to that newly created album, verify state change
    old_item = album.item
    new_item = dict(album.item, postCount=1)
    album_manager.on_album_add_edit_sync_delete_at(album.id, new_item=new_item, old_item=old_item)
    album.refresh_item()
    assert 'gsiK1PartitionKey' not in album.item
    assert 'gsiK1SortKey' not in album.item

    # fire for another post added to album, verify no-op
    old_item = dict(album.item, postCount=1)
    new_item = dict(album.item, postCount=2)
    with patch.object(album_manager, 'dynamo') as mock_dynamo:
        album_manager.on_album_add_edit_sync_delete_at(album.id, new_item=new_item, old_item=old_item)
    assert mock_dynamo.mock_calls == []
    assert 'gsiK1PartitionKey' not in album.item
    assert 'gsiK1SortKey' not in album.item

    # fire for post removed from that newly created album
    old_item = dict(album.item, postCount=1)
    new_item = dict(album.item, postCount=0)
    album_manager.on_album_add_edit_sync_delete_at(album.id, new_item=new_item, old_item=old_item)
    album.refresh_item()
    assert 'gsiK1PartitionKey' in album.item
    assert 'gsiK1SortKey' in album.item

    # fire a no-op with no posts, verify
    old_item = dict(album.item, postCount=0)
    new_item = dict(album.item)
    with patch.object(album_manager, 'dynamo') as mock_dynamo:
        album_manager.on_album_add_edit_sync_delete_at(album.id, new_item=new_item, old_item=old_item)
    assert mock_dynamo.mock_calls == []
    assert 'gsiK1PartitionKey' in album.item
    assert 'gsiK1SortKey' in album.item
