import logging
import uuid
from unittest import mock

import pytest

from app.models.user.enums import UserStatus
from app.utils import image_size


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    user = user_manager.create_cognito_only_user(user_id, username)
    user.follow_manager = mock.Mock(user.follow_manager)
    user.post_manager = mock.Mock(user.post_manager)
    user.comment_manager = mock.Mock(user.comment_manager)
    user.like_manager = mock.Mock(user.like_manager)
    user.album_manager = mock.Mock(user.album_manager)
    user.card_manager = mock.Mock(user.card_manager)
    user.block_manager = mock.Mock(user.block_manager)
    user.chat_manager = mock.Mock(user.chat_manager)
    yield user


@pytest.fixture
def user2(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


def test_delete_user_removes_item_from_dynamo(user):
    user.delete()
    assert user.item['userId'] == user.id
    assert user.item['userStatus'] == UserStatus.DELETING
    assert user.refresh_item().item is None


def test_delete_user_skip_cognito_releases_username(user, user2):
    # moto cognito has not yet implemented admin_delete_user_attributes
    user.cognito_client.user_pool_client.admin_delete_user_attributes = mock.Mock()

    # release our username by deleting our user
    username = user.item['username']
    user.delete(skip_cognito=True)

    # verify the username is now available by adding it to another
    user2.update_username(username)
    assert user2.item['username'] == username


def test_delete_user_skip_cognito_no_entry_in_user_pool(user, caplog):
    # configure the user pool to behave as if there is no entry for this user
    # note that moto cognito has not yet implemented admin_delete_user_attributes
    exception = user.cognito_client.user_pool_client.exceptions.UserNotFoundException({}, None)
    user.cognito_client.clear_user_attribute = mock.Mock(side_effect=exception)

    with caplog.at_level(logging.WARNING):
        user.delete(skip_cognito=True)

    # verify the issue was logged
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == 'WARNING'
    assert 'No cognito user pool entry found' in caplog.records[0].msg

    # verify final state
    assert user.item['userId'] == user.id
    assert user.item['userStatus'] == UserStatus.DELETING
    assert user.refresh_item().item is None


def test_delete_user_clears_cognito(user, cognito_client):
    assert cognito_client.get_user_attributes(user.id)
    user.delete()
    with pytest.raises(cognito_client.user_pool_client.exceptions.UserNotFoundException):
        cognito_client.get_user_attributes(user.id)


def test_delete_user_with_profile_pic(user):
    post_id = 'mid'
    photo_data = b'this is an image'
    content_type = 'image/jpeg'

    # add a profile pic of all sizes for that user
    paths = [user.get_photo_path(size, photo_post_id=post_id) for size in image_size.JPEGS]
    for path in paths:
        user.s3_uploads_client.put_object(path, photo_data, content_type)
    user.dynamo.set_user_photo_post_id(user.id, post_id)
    user.refresh_item()

    # verify s3 was populated, dynamo set
    for size in image_size.JPEGS:
        path = user.get_photo_path(size)
        assert user.s3_uploads_client.exists(path)
    assert 'photoPostId' in user.item

    # moto cognito has not yet implemented admin_delete_user_attributes
    user.cognito_client.user_pool_client.admin_delete_user_attributes = mock.Mock()

    # delete the user
    user.delete()

    # verify the profile pic got removed from s3
    for path in paths:
        assert not user.s3_uploads_client.exists(path)


def test_delete_user_managers_all_called(user):
    # check starting state
    assert user.follow_manager.mock_calls == []
    assert user.post_manager.mock_calls == []
    assert user.comment_manager.mock_calls == []
    assert user.like_manager.mock_calls == []
    assert user.album_manager.mock_calls == []
    assert user.card_manager.mock_calls == []
    assert user.block_manager.mock_calls == []
    assert user.chat_manager.mock_calls == []

    # delete user, check final state
    user.delete()
    assert user.follow_manager.mock_calls == [
        mock.call.reset_followed_items(user.id),
        mock.call.reset_follower_items(user.id),
    ]
    assert user.post_manager.mock_calls == [
        mock.call.unflag_all_by_user(user.id),
        mock.call.delete_all_by_user(user.id),
    ]
    assert user.comment_manager.mock_calls == [
        mock.call.unflag_all_by_user(user.id),
        mock.call.delete_all_by_user(user.id),
    ]
    assert user.like_manager.mock_calls == [
        mock.call.dislike_all_by_user(user.id),
    ]
    assert user.album_manager.mock_calls == [
        mock.call.delete_all_by_user(user.id),
    ]
    assert user.card_manager.mock_calls == [
        mock.call.truncate_cards(user.id),
    ]
    assert user.block_manager.mock_calls == [
        mock.call.unblock_all_blocks(user.id),
    ]
    assert user.chat_manager.mock_calls == [
        mock.call.leave_all_chats(user.id),
    ]
