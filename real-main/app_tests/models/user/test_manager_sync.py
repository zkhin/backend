import logging
from unittest.mock import call, patch
from uuid import uuid4

import pytest

from app.models.card.specs import ChatCardSpec, RequestedFollowersCardSpec
from app.models.user.enums import UserStatus


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user


@pytest.fixture
def chat(chat_manager, user, user2):
    yield chat_manager.add_direct_chat(str(uuid4()), user.id, user2.id)


@pytest.mark.parametrize(
    'method_name, check_method_name, log_pattern',
    [
        [
            'sync_user_status_due_to_chat_messages',
            'is_forced_disabling_criteria_met_by_chat_messages',
            'due to chatMessages',
        ],
        ['sync_user_status_due_to_comments', 'is_forced_disabling_criteria_met_by_comments', 'due to comments'],
        ['sync_user_status_due_to_posts', 'is_forced_disabling_criteria_met_by_posts', 'due to posts'],
    ],
)
def test_sync_user_status_due_to(user_manager, user, method_name, check_method_name, log_pattern, caplog):
    # test does not call
    with patch.object(user, check_method_name, return_value=False):
        with patch.object(user_manager, 'init_user', return_value=user):
            with caplog.at_level(logging.WARNING):
                getattr(user_manager, method_name)(user.id, user.item, user.item)
    assert len(caplog.records) == 0
    assert user.refresh_item().status == UserStatus.ACTIVE

    # test does call
    with patch.object(user, check_method_name, return_value=True):
        with patch.object(user_manager, 'init_user', return_value=user):
            with caplog.at_level(logging.WARNING):
                getattr(user_manager, method_name)(user.id, user.item, user.item)
    assert len(caplog.records) == 1
    assert 'USER_FORCE_DISABLED' in caplog.records[0].msg
    assert user.id in caplog.records[0].msg
    assert user.username in caplog.records[0].msg
    assert log_pattern in caplog.records[0].msg
    assert user.refresh_item().status == UserStatus.DISABLED


@pytest.mark.parametrize(
    'method_name, card_spec_class, dynamo_attribute',
    [
        ['sync_requested_followers_card', RequestedFollowersCardSpec, 'followersRequestedCount'],
        ['sync_chats_with_new_messages_card', ChatCardSpec, 'chatsWithUnviewedMessagesCount'],
    ],
)
def test_sync_card_with_count(user_manager, user, method_name, card_spec_class, dynamo_attribute):
    card_id = card_spec_class(user.id).card_id
    assert user.item.get(dynamo_attribute) is None

    # refresh with None
    with patch.object(user_manager, 'card_manager') as card_manager_mock:
        getattr(user_manager, method_name)(user.id, user.item, user.item)
    card_spec = card_manager_mock.mock_calls[0].args[0]
    assert card_spec.card_id == card_id
    assert card_manager_mock.mock_calls == [call.remove_card_by_spec_if_exists(card_spec)]

    # refresh with zero
    user.item[dynamo_attribute] = 0
    with patch.object(user_manager, 'card_manager') as card_manager_mock:
        getattr(user_manager, method_name)(user.id, user.item, user.item)
    card_spec = card_manager_mock.mock_calls[0].args[0]
    assert card_spec.card_id == card_id
    assert card_manager_mock.mock_calls == [call.remove_card_by_spec_if_exists(card_spec)]

    # refresh with one
    user.item[dynamo_attribute] = 1
    with patch.object(user_manager, 'card_manager') as card_manager_mock:
        getattr(user_manager, method_name)(user.id, user.item, user.item)
    card_spec = card_manager_mock.mock_calls[0].args[0]
    assert card_spec.card_id == card_id
    assert ' 1 ' in card_spec.title
    assert card_manager_mock.mock_calls == [call.add_or_update_card_by_spec(card_spec)]

    # refresh with two
    user.item[dynamo_attribute] = 2
    with patch.object(user_manager, 'card_manager') as card_manager_mock:
        getattr(user_manager, method_name)(user.id, user.item, user.item)
    card_spec = card_manager_mock.mock_calls[0].args[0]
    assert card_spec.card_id == card_id
    assert ' 2 ' in card_spec.title
    assert card_manager_mock.mock_calls == [call.add_or_update_card_by_spec(card_spec)]


def test_sync_elasticsearch(user_manager, user):
    with patch.object(user_manager, 'elasticsearch_client') as elasticsearch_client_mock:
        user_manager.sync_elasticsearch(user.id, {'username': 'spock'}, 'garbage')
    assert elasticsearch_client_mock.mock_calls == [call.put_user(user.id, 'spock', None)]

    with patch.object(user_manager, 'elasticsearch_client') as elasticsearch_client_mock:
        user_manager.sync_elasticsearch(user.id, {'username': 'sp', 'fullName': 'fn'}, 'garbage')
    assert elasticsearch_client_mock.mock_calls == [call.put_user(user.id, 'sp', 'fn')]


@pytest.mark.parametrize(
    'method_name, pinpoint_attribute, dynamo_attribute',
    [['sync_pinpoint_email', 'EMAIL', 'email'], ['sync_pinpoint_phone', 'SMS', 'phoneNumber']],
)
def test_sync_pinpoint_attribute(user_manager, user, method_name, pinpoint_attribute, dynamo_attribute):
    # test no value
    user.item.pop(dynamo_attribute, None)
    with patch.object(user_manager, 'pinpoint_client') as pinpoint_client_mock:
        getattr(user_manager, method_name)(user.id, user.item, user.item)
    assert pinpoint_client_mock.mock_calls == [call.delete_user_endpoint(user.id, pinpoint_attribute)]

    # test with value
    user.item[dynamo_attribute] = 'the-val'
    with patch.object(user_manager, 'pinpoint_client') as pinpoint_client_mock:
        getattr(user_manager, method_name)(user.id, user.item, user.item)
    assert pinpoint_client_mock.mock_calls == [call.update_user_endpoint(user.id, pinpoint_attribute, 'the-val')]


def test_sync_pinpoint_user_status(user_manager, user):
    user.item['userStatus'] = UserStatus.ACTIVE
    with patch.object(user_manager, 'pinpoint_client') as pinpoint_client_mock:
        user_manager.sync_pinpoint_user_status(user.id, user.item, user.item)
    assert pinpoint_client_mock.mock_calls == [call.enable_user_endpoints(user.id)]

    user.item['userStatus'] = UserStatus.DISABLED
    with patch.object(user_manager, 'pinpoint_client') as pinpoint_client_mock:
        user_manager.sync_pinpoint_user_status(user.id, user.item, user.item)
    assert pinpoint_client_mock.mock_calls == [call.disable_user_endpoints(user.id)]

    user.item['userStatus'] = UserStatus.DELETING
    with patch.object(user_manager, 'pinpoint_client') as pinpoint_client_mock:
        user_manager.sync_pinpoint_user_status(user.id, user.item, user.item)
    assert pinpoint_client_mock.mock_calls == [call.delete_user_endpoints(user.id)]


def test_sync_chats_with_unviewed_messages_count_chat_member_added(user_manager, chat, user):
    assert user.refresh_item().item.get('chatsWithUnviewedMessagesCount', 0) == 0

    # sync add of member with no unviewed message count, verify
    new_item = chat.member_dynamo.get(chat.id, user.id)
    assert 'messagesUnviewedCount' not in new_item
    user_manager.sync_chats_with_unviewed_messages_count(chat.id, new_item=new_item, old_item={})
    assert user.refresh_item().item.get('chatsWithUnviewedMessagesCount', 0) == 0

    # synd add of member with some unviewed message count, verify
    new_item = chat.member_dynamo.increment_messages_unviewed_count(chat.id, user.id)
    assert new_item['messagesUnviewedCount'] == 1
    user_manager.sync_chats_with_unviewed_messages_count(chat.id, new_item=new_item, old_item={})


def test_sync_chats_with_unviewed_messages_count_chat_member_edited(user_manager, chat, user):
    assert user.refresh_item().item.get('chatsWithUnviewedMessagesCount', 0) == 0

    # sync edit of member from no unviewed message count to some, verify
    item1 = chat.member_dynamo.get(chat.id, user.id)
    assert 'messagesUnviewedCount' not in item1
    item2 = chat.member_dynamo.increment_messages_unviewed_count(chat.id, user.id)
    assert item2['messagesUnviewedCount'] == 1
    user_manager.sync_chats_with_unviewed_messages_count(chat.id, new_item=item2, old_item=item1)
    assert user.refresh_item().item.get('chatsWithUnviewedMessagesCount', 0) == 1

    # sync edit of member from some unviewed message count some more, verify
    item3 = chat.member_dynamo.increment_messages_unviewed_count(chat.id, user.id)
    assert item3['messagesUnviewedCount'] == 2
    user_manager.sync_chats_with_unviewed_messages_count(chat.id, new_item=item3, old_item=item2)
    assert user.refresh_item().item.get('chatsWithUnviewedMessagesCount', 0) == 1

    # sync edit of member from some unviewed message count to none, verify
    user_manager.sync_chats_with_unviewed_messages_count(chat.id, new_item=item1, old_item=item3)
    assert user.refresh_item().item.get('chatsWithUnviewedMessagesCount', 0) == 0


def test_sync_chats_with_unviewed_messages_count_chat_member_deleted(user_manager, chat, user, caplog):
    user.dynamo.increment_chats_with_unviewed_messages_count(user.id)
    assert user.refresh_item().item.get('chatsWithUnviewedMessagesCount', 0) == 1

    # sync delete of member with no unviewed message count, verify
    old_item = chat.member_dynamo.get(chat.id, user.id)
    assert 'messagesUnviewedCount' not in old_item
    user_manager.sync_chats_with_unviewed_messages_count(chat.id, new_item={}, old_item=old_item)
    assert user.refresh_item().item.get('chatsWithUnviewedMessagesCount', 0) == 1

    # sync delete of member with some unviewed message count, verify
    old_item = chat.member_dynamo.increment_messages_unviewed_count(chat.id, user.id)
    assert old_item['messagesUnviewedCount'] == 1
    user_manager.sync_chats_with_unviewed_messages_count(chat.id, new_item={}, old_item=old_item)
    assert user.refresh_item().item.get('chatsWithUnviewedMessagesCount', 0) == 0

    # sync delete of member with some unviewed message count, verify fails softly
    with caplog.at_level(logging.WARNING):
        user_manager.sync_chats_with_unviewed_messages_count(chat.id, new_item={}, old_item=old_item)
    assert len(caplog.records) == 1
    assert 'Failed to decrement' in caplog.records[0].msg
    assert 'chatsWithUnviewedMessagesCount' in caplog.records[0].msg
    assert user.id in caplog.records[0].msg
