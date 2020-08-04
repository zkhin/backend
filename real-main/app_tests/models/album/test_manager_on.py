from unittest.mock import call, patch
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


@pytest.fixture
def post(post_manager, user, image_data_b64):
    yield post_manager.add_post(user, str(uuid4()), PostType.IMAGE, image_input={'imageData': image_data_b64})


album2 = album


def test_on_album_delete_delete_album_art(album_manager, post, user, album, image_data_b64):
    # fire for a delete of an album with no art, verify no error
    assert 'artHash' not in album.item
    album_manager.on_album_delete_delete_album_art(album.id, old_item=album.item)

    # add a post with an image to the album to get some art in S3, verify
    post = post.set_album(album.id)
    album_manager.on_post_album_change_update_art_if_needed(post.id, new_item=post.item)
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


def test_on_post_album_change_update_art_if_needed(album_manager, user, album, album2, post, post_manager):
    # verify no calls for creating a pending post in album
    pending_post = post_manager.add_post(user, str(uuid4()), PostType.IMAGE, album_id=album.id)
    with patch.object(album_manager, 'get_album') as get_album_mock:
        album_manager.on_post_album_change_update_art_if_needed(pending_post.id, new_item=pending_post.item)
    assert get_album_mock.mock_calls == []

    # verify no calls for changing what album that pending post is in
    old_item = pending_post.item.copy()
    pending_post.set_album(album2.id)
    with patch.object(album_manager, 'get_album') as get_album_mock:
        album_manager.on_post_album_change_update_art_if_needed(
            pending_post.id, new_item=pending_post.item, old_item=old_item
        )
    assert get_album_mock.mock_calls == []

    # verify no calls for deleting that pending post in album
    with patch.object(album_manager, 'get_album') as get_album_mock:
        album_manager.on_post_album_change_update_art_if_needed(pending_post.id, old_item=pending_post.item)
    assert get_album_mock.mock_calls == []

    # verify calls for adding a completed post to an album
    old_item = post.item.copy()
    post.set_album(album.id)
    with patch.object(album_manager, 'get_album') as get_album_mock:
        album_manager.on_post_album_change_update_art_if_needed(post.id, new_item=post.item, old_item=old_item)
    assert get_album_mock.mock_calls == [call(album.id), call().update_art_if_needed()]

    # verify calls for archiving post in an album
    old_item = post.item.copy()
    post.archive()
    with patch.object(album_manager, 'get_album') as get_album_mock:
        album_manager.on_post_album_change_update_art_if_needed(post.id, new_item=post.item, old_item=old_item)
    assert get_album_mock.mock_calls == [call(album.id), call().update_art_if_needed()]

    # verify calls for restoring post in an album
    old_item = post.item.copy()
    post.restore()
    with patch.object(album_manager, 'get_album') as get_album_mock:
        album_manager.on_post_album_change_update_art_if_needed(post.id, new_item=post.item, old_item=old_item)
    assert get_album_mock.mock_calls == [call(album.id), call().update_art_if_needed()]

    # verify calls for changing which album post is in
    old_item = post.item.copy()
    post.set_album(album2.id)
    with patch.object(album_manager, 'get_album') as get_album_mock:
        album_manager.on_post_album_change_update_art_if_needed(post.id, new_item=post.item, old_item=old_item)
    assert get_album_mock.mock_calls == [
        call(album2.id),
        call().update_art_if_needed(),
        call(album.id),
        call().update_art_if_needed(),
    ]

    # verify calls for changing postion of post in album
    old_item = {**post.item, 'gsiK3SortKey': -0.57}  # gsiK3SortKey is albumRank
    with patch.object(album_manager, 'get_album') as get_album_mock:
        album_manager.on_post_album_change_update_art_if_needed(post.id, new_item=post.item, old_item=old_item)
    assert get_album_mock.mock_calls == [call(album2.id), call().update_art_if_needed()]

    # verify calls for deleting post
    with patch.object(album_manager, 'get_album') as get_album_mock:
        album_manager.on_post_album_change_update_art_if_needed(post.id, old_item=post.item)
    assert get_album_mock.mock_calls == [call(album2.id), call().update_art_if_needed()]
