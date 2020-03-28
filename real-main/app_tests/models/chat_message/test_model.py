from unittest.mock import Mock, call

import pendulum
import pytest

from app.models.block.enums import BlockStatus
from app.models.view.enums import ViewedStatus


@pytest.fixture
def user1(user_manager):
    yield user_manager.create_cognito_only_user('pbuid', 'pbUname')


@pytest.fixture
def user2(user_manager):
    yield user_manager.create_cognito_only_user('pbuid2', 'pbUname2')


@pytest.fixture
def chat(chat_manager, user1, user2):
    yield chat_manager.add_direct_chat('cid', user1.id, user2.id)


@pytest.fixture
def message(chat_message_manager, chat, user1):
    message_id = 'mid'
    text = 'lore ipsum'
    yield chat_message_manager.add_chat_message(message_id, text, chat.id, user1.id)


def test_chat_message_serialize(message, user1, user2, chat, view_manager):
    # check that user1 has viewed it (since they wrote it) and user2 has not
    message.serialize(user1.id)['viewedStatus'] == ViewedStatus.VIEWED
    message.serialize(user1.id)['author']['blockerStatus'] == BlockStatus.SELF
    message.serialize(user2.id)['viewedStatus'] == ViewedStatus.NOT_VIEWED
    message.serialize(user2.id)['author']['blockerStatus'] == BlockStatus.NOT_BLOCKING

    # user2 reports to have viewed it, check that reflects in the viewedStatus
    view_manager.record_views('chat_message', [message.id], user2.id)
    message.serialize(user2.id)['viewedStatus'] == ViewedStatus.VIEWED


def test_chat_message_edit(message, chat, user1, user2):
    # check starting state
    chat.refresh_item()
    assert chat.item['messageCount'] == 1
    assert chat.item['lastMessageActivityAt'] == message.item['createdAt']
    assert message.item['text'] == 'lore ipsum'
    assert message.item['textTags'] == []
    assert 'lastEditedAt' not in message.item

    # check starting chat membership sort order state
    assert chat.dynamo.get_chat_membership(chat.id, user1.id)['gsiK2SortKey'] == 'chat/' + message.item['createdAt']
    assert chat.dynamo.get_chat_membership(chat.id, user2.id)['gsiK2SortKey'] == 'chat/' + message.item['createdAt']

    # edit the message
    username = user1.item['username']
    new_text = f'whats up with @{username}?'
    now = pendulum.now('utc')
    message.edit(new_text, now=now)
    assert message.item['text'] == new_text
    assert message.item['textTags'] == [{'tag': f'@{username}', 'userId': user1.id}]
    assert pendulum.parse(message.item['lastEditedAt']) == now

    # check state in dynamo
    chat.refresh_item()
    assert chat.item['messageCount'] == 1
    assert chat.item['lastMessageActivityAt'] == message.item['lastEditedAt']
    message.refresh_item()
    assert message.item['text'] == new_text
    assert message.item['textTags'] == [{'tag': f'@{username}', 'userId': user1.id}]
    assert pendulum.parse(message.item['lastEditedAt']) == now

    # check final chat membership sort order state
    assert pendulum.parse(chat.dynamo.get_chat_membership(chat.id, user1.id)['gsiK2SortKey'][len('chat/'):]) == now
    assert pendulum.parse(chat.dynamo.get_chat_membership(chat.id, user2.id)['gsiK2SortKey'][len('chat/'):]) == now


def test_chat_message_delete(message, chat, user1, user2):
    # double check starting state
    chat.refresh_item()
    message.refresh_item()
    assert chat.item['messageCount'] == 1
    assert chat.item['lastMessageActivityAt'] == message.item['createdAt']
    assert message.item

    # check starting chat membership sort order state
    assert chat.dynamo.get_chat_membership(chat.id, user1.id)['gsiK2SortKey'] == 'chat/' + message.item['createdAt']
    assert chat.dynamo.get_chat_membership(chat.id, user2.id)['gsiK2SortKey'] == 'chat/' + message.item['createdAt']

    # delete the message
    now = pendulum.now('utc')
    message.delete(now=now)
    # we need to be able to serialize the gql response, so keep the in-mem item around
    assert message.item

    # check state in dynamo
    chat.refresh_item()
    assert chat.item['messageCount'] == 0
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    message.refresh_item()
    assert message.item is None

    # check final chat membership sort order state
    assert pendulum.parse(chat.dynamo.get_chat_membership(chat.id, user1.id)['gsiK2SortKey'][len('chat/'):]) == now
    assert pendulum.parse(chat.dynamo.get_chat_membership(chat.id, user2.id)['gsiK2SortKey'][len('chat/'):]) == now


def test_chat_message_trigger_notification(message, chat, user1):
    # trigger a notificaiton and check our mock client was called as expected
    message.appsync_client = Mock()
    message.trigger_notification('ntype')
    expected_input = {
        'messageId': 'mid',
        'chatId': chat.id,
        'authorUserId': user1.id,
        'type': 'ntype',
        'text': 'lore ipsum',
        'textTaggedUserIds': [],
        'createdAt': message.item['createdAt'],
        'lastEditedAt': None
    }
    message.appsync_client.mock_calls == [
        call.send(message.trigger_notification_mutation, {'input': expected_input})
    ]
