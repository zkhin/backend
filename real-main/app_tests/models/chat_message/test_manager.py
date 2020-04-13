import uuid

import pendulum
import pytest


@pytest.fixture
def user(user_manager, cognito_client):
    user_id = str(uuid.uuid4())
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username=user_id)
    yield user_manager.create_cognito_only_user(user_id, str(uuid.uuid4())[:8])


user2 = user
user3 = user


@pytest.fixture
def chat(chat_manager, user2, user3):
    yield chat_manager.add_direct_chat('cid', user2.id, user3.id)


def test_add_chat_message(chat_message_manager, user, chat, user2, user3):
    username = user.item['username']
    text = f'whats up with @{username}?'
    message_id = 'mid'
    user_id = 'uid'

    # check message count starts off at zero
    assert 'messageCount' not in chat.item
    assert 'lastMessageActivityAt' not in chat.item

    # check the chat memberships start off with correct lastMessageActivityAt
    assert chat.dynamo.get_chat_membership(chat.id, user2.id)['gsiK2SortKey'] == 'chat/' + chat.item['createdAt']
    assert chat.dynamo.get_chat_membership(chat.id, user3.id)['gsiK2SortKey'] == 'chat/' + chat.item['createdAt']

    # add the message, check it looks ok
    now = pendulum.now('utc')
    now_str = now.to_iso8601_string()
    message = chat_message_manager.add_chat_message(message_id, text, chat.id, user_id, now=now)
    assert message.id == message_id
    assert message.user_id == user_id
    assert message.item['createdAt'] == now_str
    assert message.item['text'] == text
    assert message.item['textTags'] == [{'tag': f'@{username}', 'userId': user.id}]

    # check the chat was altered correctly
    chat.refresh_item()
    assert chat.item['messageCount'] == 1
    assert chat.item['lastMessageActivityAt'] == now_str

    # check the chat memberships lastMessageActivityAt was updated
    assert chat.dynamo.get_chat_membership(chat.id, user2.id)['gsiK2SortKey'] == 'chat/' + now_str
    assert chat.dynamo.get_chat_membership(chat.id, user3.id)['gsiK2SortKey'] == 'chat/' + now_str


def test_truncate_chat_messages(chat_message_manager, user, chat, view_manager):
    # add two messsages
    message_id_1, message_id_2 = 'mid1', 'mid2'

    message_1 = chat_message_manager.add_chat_message(message_id_1, 'lore', chat.id, user.id)
    assert message_1.id == message_id_1

    message_2 = chat_message_manager.add_chat_message(message_id_2, 'ipsum', chat.id, user.id)
    assert message_2.id == message_id_2

    # add some views to the messsages, verify we see them in the db
    view_manager.record_views('chat_message', ['mid1', 'mid2', 'mid1'], 'uid')
    assert view_manager.dynamo.get_view('chatMessage/mid1', 'uid')
    assert view_manager.dynamo.get_view('chatMessage/mid2', 'uid')

    # check the chat total is correct
    chat.refresh_item()
    assert chat.item['messageCount'] == 2

    # truncate the messages
    chat_message_manager.truncate_chat_messages(chat.id)

    # check the chat itself was not deleted, including the message total
    chat.refresh_item()
    assert chat.item['messageCount'] == 2

    # check the two messages have been deleted
    assert chat_message_manager.get_chat_message(message_id_1) is None
    assert chat_message_manager.get_chat_message(message_id_2) is None

    # check the message views have also been deleted
    assert view_manager.dynamo.get_view('chatMessage/mid1', 'uid') is None
    assert view_manager.dynamo.get_view('chatMessage/mid2', 'uid') is None


def test_add_system_message(chat_message_manager, chat, appsync_client, user2, user3):
    text = 'sample sample'

    # check message count starts off at zero
    assert 'messageCount' not in chat.item
    assert 'lastMessageActivityAt' not in chat.item

    # add the message, check it looks ok
    now = pendulum.now('utc')
    message = chat_message_manager.add_system_message(chat.id, text, now=now)
    assert message.id
    assert message.user_id is None
    assert message.item['createdAt'] == now.to_iso8601_string()
    assert message.item['text'] == text
    assert message.item['textTags'] == []

    # check the chat was altered correctly
    chat.refresh_item()
    assert chat.item['messageCount'] == 1
    assert chat.item['lastMessageActivityAt'] == now.to_iso8601_string()

    # check the message notification was triggered
    assert len(appsync_client.send.call_args_list) == 2
    assert len(appsync_client.send.call_args_list[0].args) == 2
    variables = appsync_client.send.call_args_list[0].args[1]
    assert variables['input']['userId'] == user2.id
    assert variables['input']['messageId'] == message.id
    assert variables['input']['authorUserId'] is None
    assert variables['input']['type'] == 'ADDED'
    assert len(appsync_client.send.call_args_list[1].args) == 2
    variables = appsync_client.send.call_args_list[1].args[1]
    assert variables['input']['userId'] == user3.id
    assert variables['input']['messageId'] == message.id
    assert variables['input']['authorUserId'] is None
    assert variables['input']['type'] == 'ADDED'


def test_add_system_message_group_created(chat_message_manager, chat, user):
    assert user.username

    # check message count starts off at zero
    assert 'messageCount' not in chat.item

    # add the message, check it looks ok
    message = chat_message_manager.add_system_message_group_created(chat.id, user.id)
    assert message.item['text'] == f'@{user.username} created the group'
    assert message.item['textTags'] == [{'tag': f'@{user.username}', 'userId': user.id}]

    # check the chat was altered correctly
    chat.refresh_item()
    assert chat.item['messageCount'] == 1

    # add another message, check it looks ok
    message = chat_message_manager.add_system_message_group_created(chat.id, user.id, name='group name')
    assert message.item['text'] == f'@{user.username} created the group "group name"'
    assert message.item['textTags'] == [{'tag': f'@{user.username}', 'userId': user.id}]

    # check the chat was altered correctly
    chat.refresh_item()
    assert chat.item['messageCount'] == 2


def test_add_system_message_added_to_group(chat_message_manager, chat, user, user2, user3):
    assert user.username
    assert user2.username
    assert user3.username

    # check message count starts off at zero
    assert 'messageCount' not in chat.item

    # can't add no users
    with pytest.raises(AssertionError):
        chat_message_manager.add_system_message_added_to_group(chat.id, user.id, [])

    # add one user
    message = chat_message_manager.add_system_message_added_to_group(chat.id, user.id, [user2])
    assert message.item['text'] == f'@{user.username} added @{user2.username} to the group'
    assert len(message.item['textTags']) == 2

    # add two users
    message = chat_message_manager.add_system_message_added_to_group(chat.id, user.id, [user2, user3])
    assert message.item['text'] == f'@{user.username} added @{user2.username} and @{user3.username} to the group'
    assert len(message.item['textTags']) == 3

    # add three users
    message = chat_message_manager.add_system_message_added_to_group(chat.id, user.id, [user2, user3, user])
    assert message.item['text'] == \
        f'@{user.username} added @{user2.username}, @{user3.username} and @{user.username} to the group'
    assert len(message.item['textTags']) == 3

    # check the chat was altered correctly
    chat.refresh_item()
    assert chat.item['messageCount'] == 3


def test_add_system_message_left_group(chat_message_manager, chat, user):
    assert user.username

    # check message count starts off at zero
    assert 'messageCount' not in chat.item

    # user leaves
    message = chat_message_manager.add_system_message_left_group(chat.id, user.id)
    assert message.item['text'] == f'@{user.username} left the group'
    assert len(message.item['textTags']) == 1

    # check the chat was altered correctly
    chat.refresh_item()
    assert chat.item['messageCount'] == 1


def test_add_system_message_group_name_edited(chat_message_manager, chat, user):
    assert user.username

    # check message count starts off at zero
    assert 'messageCount' not in chat.item

    # user changes the name
    message = chat_message_manager.add_system_message_group_name_edited(chat.id, user.id, '4eva')
    assert message.item['text'] == f'@{user.username} changed the name of the group to "4eva"'
    assert len(message.item['textTags']) == 1

    # user deletes the name the name
    message = chat_message_manager.add_system_message_group_name_edited(chat.id, user.id, None)
    assert message.item['text'] == f'@{user.username} deleted the name of the group'
    assert len(message.item['textTags']) == 1

    # check the chat was altered correctly
    chat.refresh_item()
    assert chat.item['messageCount'] == 2
