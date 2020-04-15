import base64
import json
from unittest.mock import Mock, call
import os

import pendulum
import pytest

from app.models.block.enums import BlockStatus
from app.models.post.enums import PostType
from app.models.view.enums import ViewedStatus

grant_path = os.path.join(os.path.dirname(__file__), '..', '..', 'fixtures', 'grant.jpg')


@pytest.fixture
def grant_data_b64():
    with open(grant_path, 'rb') as fh:
        yield base64.b64encode(fh.read())


@pytest.fixture
def user1(user_manager, post_manager, grant_data_b64, cognito_client):
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username='pbuid')
    user = user_manager.create_cognito_only_user('pbuid', 'pbUname')
    # give the user a profile photo so that it will show up in the message notification trigger calls
    post = post_manager.add_post(user.id, 'pid', PostType.IMAGE, image_input={'imageData': grant_data_b64})
    user.update_photo(post.id)
    yield user


@pytest.fixture
def user2(user_manager, cognito_client):
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username='pbuid2')
    yield user_manager.create_cognito_only_user('pbuid2', 'pbUname2')


@pytest.fixture
def user3(user_manager, cognito_client):
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username='pbuid3')
    yield user_manager.create_cognito_only_user('pbuid3', 'pbUname3')


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


def test_get_author_encoded(chat_message_manager, user1, user2, user3, chat, block_manager):
    # regular message
    message = chat_message_manager.add_chat_message('mid', 'lore', chat.id, user1.id)
    author_encoded = message.get_author_encoded(user3.id)
    assert author_encoded
    author_serialized = json.loads(author_encoded)
    assert author_serialized['userId'] == user1.id
    assert author_serialized['username'] == user1.username
    assert author_serialized['photoPostId'] == user1.item['photoPostId']
    assert author_serialized['blockerStatus'] == 'NOT_BLOCKING'
    assert author_serialized['blockedStatus'] == 'NOT_BLOCKING'

    # add a blocking relationship
    block_manager.block(user1, user3)
    assert message.get_author_encoded(user3.id) is None

    # test the blocking relationship in the other direction
    message = chat_message_manager.add_chat_message('mid2', 'lore', chat.id, user3.id)
    assert message.get_author_encoded(user1.id) is None

    # test with no author (simulates a system message)
    message = chat_message_manager.add_chat_message('mid3', 'lore', chat.id, user2.id)
    assert message.get_author_encoded(user1.id)
    message._author = None
    assert message.get_author_encoded(user1.id) is None


def test_trigger_notification(message, chat, user1, user2, appsync_client):
    appsync_client.reset_mock()

    # trigger a notificaiton and check our mock client was called as expected
    message.trigger_notification('ntype', user2.id)
    assert len(appsync_client.mock_calls) == 1
    assert len(appsync_client.send.call_args.kwargs) == 0
    args = appsync_client.send.call_args.args
    assert len(args) == 2
    assert args[0] == message.trigger_notification_mutation
    assert list(args[1].keys()) == ['input']
    assert len(args[1]['input']) == 10
    assert args[1]['input']['userId'] == user2.id
    assert args[1]['input']['messageId'] == 'mid'
    assert args[1]['input']['chatId'] == chat.id
    assert args[1]['input']['authorUserId'] == user1.id
    assert json.loads(args[1]['input']['authorEncoded'])['userId'] == user1.id
    assert json.loads(args[1]['input']['authorEncoded'])['username'] == user1.username
    assert args[1]['input']['type'] == 'ntype'
    assert args[1]['input']['text'] == message.item['text']
    assert args[1]['input']['textTaggedUserIds'] == []
    assert args[1]['input']['createdAt'] == message.item['createdAt']
    assert args[1]['input']['lastEditedAt'] is None


def test_trigger_notification_blocking_relationship(chat_message_manager, chat, user1, user2, appsync_client,
                                                    block_manager):
    # user1 triggers a message notification that user2 recieves (in a group chat)
    message1 = chat_message_manager.add_chat_message('mid3', 'lore', chat.id, user1.id)
    message2 = chat_message_manager.add_chat_message('mid4', 'lore', chat.id, user2.id)

    # user1 blocks user2
    block_manager.block(user1, user2)

    message1.trigger_notification('ntype', user2.id)
    assert appsync_client.send.call_args.args[1]['input']['userId'] == user2.id
    assert appsync_client.send.call_args.args[1]['input']['authorUserId'] == user1.id
    assert appsync_client.send.call_args.args[1]['input']['authorEncoded'] is None

    message2.trigger_notification('ntype', user1.id)
    assert appsync_client.send.call_args.args[1]['input']['userId'] == user1.id
    assert appsync_client.send.call_args.args[1]['input']['authorUserId'] == user2.id
    assert appsync_client.send.call_args.args[1]['input']['authorEncoded'] is None


def test_trigger_notification_system_message(chat_manager, chat_message_manager, user1, appsync_client):
    group_chat = chat_manager.add_group_chat('cid', user1.id)
    appsync_client.reset_mock()
    # adding a system message triggers the notifcations automatically
    message = chat_message_manager.add_system_message_group_name_edited(group_chat.id, user1.id, 'cname')
    assert len(appsync_client.mock_calls) == 1
    assert len(appsync_client.send.call_args.kwargs) == 0
    args = appsync_client.send.call_args.args
    assert len(args) == 2
    assert args[0] == message.trigger_notification_mutation
    assert list(args[1].keys()) == ['input']
    assert len(args[1]['input']) == 10
    assert args[1]['input']['userId'] == user1.id
    assert args[1]['input']['messageId'] == message.id
    assert args[1]['input']['chatId'] == group_chat.id
    assert args[1]['input']['authorUserId'] is None
    assert args[1]['input']['authorEncoded'] is None
    assert args[1]['input']['type'] == 'ADDED'
    assert args[1]['input']['text'] == message.item['text']
    assert args[1]['input']['textTaggedUserIds'] == [{'tag': f'@{user1.username}', 'userId': user1.id}]
    assert args[1]['input']['createdAt'] == message.item['createdAt']
    assert args[1]['input']['lastEditedAt'] is None


def test_trigger_notifications_direct(message, chat, user1, user2, appsync_client):
    message.trigger_notification = Mock()
    message.trigger_notifications('ntype')
    assert message.trigger_notification.mock_calls == [call('ntype', user2.id)]


def test_trigger_notifications_user_ids(message, chat, user1, user2, user3, appsync_client):
    # trigger a notification and check that we can use user_ids param to push
    # the notifications to users that aren't found in dynamo
    message.trigger_notification = Mock()
    message.trigger_notifications('ntype', user_ids=[user2.id, user3.id])
    assert message.trigger_notification.mock_calls == [
        call('ntype', user2.id),
        call('ntype', user3.id),
    ]


def test_trigger_notifications_group(chat_manager, chat_message_manager, user1, user2, user3, appsync_client):
    # user1 creates a group chat with everyone in it
    group_chat = chat_manager.add_group_chat('cid', user1.id)
    group_chat.add(user1.id, [user2.id, user3.id])

    # user2 creates a message, trigger notificaitons on it
    message_id = 'mid'
    message = chat_message_manager.add_chat_message(message_id, 'lore', group_chat.id, user2.id)
    message.trigger_notification = Mock()
    message.trigger_notifications('ntype')
    assert message.trigger_notification.mock_calls == [
        call('ntype', user1.id),
        call('ntype', user3.id),
    ]

    # add system message, notifications are triggered automatically
    appsync_client.reset_mock()
    message = chat_message_manager.add_system_message_group_name_edited(group_chat.id, user3.id, 'cname')
    assert len(appsync_client.send.mock_calls) == 3  # one for each member of the group chat
