import logging
import uuid

import pendulum
import pytest

from app.models.card.specs import ChatCardSpec


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


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
    gsi_k2_sort_key = 'chat/' + chat.item['createdAt']
    assert chat.member_dynamo.get(chat.id, user2.id)['gsiK2SortKey'] == gsi_k2_sort_key
    assert chat.member_dynamo.get(chat.id, user3.id)['gsiK2SortKey'] == gsi_k2_sort_key

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
    assert chat.member_dynamo.get(chat.id, user2.id)['gsiK2SortKey'] == 'chat/' + now_str
    assert chat.member_dynamo.get(chat.id, user3.id)['gsiK2SortKey'] == 'chat/' + now_str


def test_truncate_chat_messages(chat_message_manager, user, chat):
    # add two messsages
    message_id_1, message_id_2 = 'mid1', 'mid2'

    message_1 = chat_message_manager.add_chat_message(message_id_1, 'lore', chat.id, user.id)
    assert message_1.id == message_id_1

    message_2 = chat_message_manager.add_chat_message(message_id_2, 'ipsum', chat.id, user.id)
    assert message_2.id == message_id_2

    # add some views to the messsages, verify we see them in the db
    chat_message_manager.record_views(['mid1', 'mid2', 'mid1'], 'uid')
    assert message_1.view_dynamo.get_view(message_1.id, 'uid')
    assert message_2.view_dynamo.get_view(message_2.id, 'uid')

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
    assert message_1.view_dynamo.get_view(message_1.id, 'uid') is None
    assert message_2.view_dynamo.get_view(message_2.id, 'uid') is None


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

    # triggers both the chat message notifications and also the cards notifications
    # check the chat message notifications were triggered correctly, skip the cards
    assert len(appsync_client.send.call_args_list) == 4
    assert len(appsync_client.send.call_args_list[1].args) == 2
    variables = appsync_client.send.call_args_list[2].args[1]
    assert variables['input']['userId'] == user2.id
    assert variables['input']['messageId'] == message.id
    assert variables['input']['authorUserId'] is None
    assert variables['input']['type'] == 'ADDED'
    assert len(appsync_client.send.call_args_list[3].args) == 2
    variables = appsync_client.send.call_args_list[3].args[1]
    assert variables['input']['userId'] == user3.id
    assert variables['input']['messageId'] == message.id
    assert variables['input']['authorUserId'] is None
    assert variables['input']['type'] == 'ADDED'


def test_add_system_message_group_created(chat_message_manager, chat, user):
    assert user.username

    # check message count starts off at zero
    assert 'messageCount' not in chat.item

    # add the message, check it looks ok
    message = chat_message_manager.add_system_message_group_created(chat.id, user)
    assert message.item['text'] == f'@{user.username} created the group'
    assert message.item['textTags'] == [{'tag': f'@{user.username}', 'userId': user.id}]

    # check the chat was altered correctly
    chat.refresh_item()
    assert chat.item['messageCount'] == 1

    # add another message, check it looks ok
    message = chat_message_manager.add_system_message_group_created(chat.id, user, name='group name')
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
        chat_message_manager.add_system_message_added_to_group(chat.id, user, [])

    # add one user
    message = chat_message_manager.add_system_message_added_to_group(chat.id, user, [user2])
    assert message.item['text'] == f'@{user.username} added @{user2.username} to the group'
    assert len(message.item['textTags']) == 2

    # add two users
    message = chat_message_manager.add_system_message_added_to_group(chat.id, user, [user2, user3])
    assert message.item['text'] == f'@{user.username} added @{user2.username} and @{user3.username} to the group'
    assert len(message.item['textTags']) == 3

    # add three users
    message = chat_message_manager.add_system_message_added_to_group(chat.id, user, [user2, user3, user])
    assert (
        message.item['text']
        == f'@{user.username} added @{user2.username}, @{user3.username} and @{user.username} to the group'
    )
    assert len(message.item['textTags']) == 3

    # check the chat was altered correctly
    chat.refresh_item()
    assert chat.item['messageCount'] == 3


def test_add_system_message_left_group(chat_message_manager, chat, user):
    assert user.username

    # check message count starts off at zero
    assert 'messageCount' not in chat.item

    # user leaves
    message = chat_message_manager.add_system_message_left_group(chat.id, user)
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
    message = chat_message_manager.add_system_message_group_name_edited(chat.id, user, '4eva')
    assert message.item['text'] == f'@{user.username} changed the name of the group to "4eva"'
    assert len(message.item['textTags']) == 1

    # user deletes the name the name
    message = chat_message_manager.add_system_message_group_name_edited(chat.id, user, None)
    assert message.item['text'] == f'@{user.username} deleted the name of the group'
    assert len(message.item['textTags']) == 1

    # check the chat was altered correctly
    chat.refresh_item()
    assert chat.item['messageCount'] == 2


def test_record_views(chat_message_manager, chat, user2, user3, caplog):
    # add three messages to the chat
    message1 = chat_message_manager.add_chat_message(str(uuid.uuid4()), 't', chat.id, user2.id)
    message2 = chat_message_manager.add_chat_message(str(uuid.uuid4()), 't', chat.id, user3.id)
    message3 = chat_message_manager.add_chat_message(str(uuid.uuid4()), 't', chat.id, user3.id)

    # user2 records on DNE message
    with caplog.at_level(logging.WARNING):
        chat_message_manager.record_views(['cid-dne'], user2.id)
    assert len(caplog.records) == 1
    assert 'cid-dne' in caplog.records[0].msg
    assert user2.id in caplog.records[0].msg
    assert message1.view_dynamo.get_view(message1.id, user2.id) is None
    assert message2.view_dynamo.get_view(message2.id, user2.id) is None
    assert message2.view_dynamo.get_view(message3.id, user2.id) is None

    # user2 records views on two of them
    assert message1.view_dynamo.get_view(message2.id, user2.id) is None
    assert message2.view_dynamo.get_view(message3.id, user2.id) is None
    chat_message_manager.record_views([message2.id, message2.id, message3.id], user2.id)
    assert message1.view_dynamo.get_view(message2.id, user2.id)['viewCount'] == 2
    assert message2.view_dynamo.get_view(message3.id, user2.id)['viewCount'] == 1

    # user3 records views on one of them, only gets records for messages they aren't author
    assert message1.view_dynamo.get_view(message1.id, user3.id) is None
    chat_message_manager.record_views([message1.id, message1.id, message2.id], user3.id)
    assert message1.view_dynamo.get_view(message1.id, user3.id)['viewCount'] == 2
    assert message1.view_dynamo.get_view(message2.id, user3.id) is None


def test_record_views_removes_card(chat_message_manager, chat, user2, user3, card_manager):
    spec2 = ChatCardSpec(user2.id)
    spec3 = ChatCardSpec(user3.id)

    # add the well-known card for both users, check starting state
    card_manager.add_card_by_spec_if_dne(spec2)
    card_manager.add_card_by_spec_if_dne(spec3)
    assert card_manager.get_card(spec2.card_id)
    assert card_manager.get_card(spec3.card_id)

    # user2 adds a message, both users views it, should remove user3's card but not user2's
    message1 = chat_message_manager.add_chat_message(str(uuid.uuid4()), 't', chat.id, user2.id)
    chat_message_manager.record_views([message1.id], user2.id)
    chat_message_manager.record_views([message1.id], user3.id)
    assert card_manager.get_card(spec2.card_id)
    assert card_manager.get_card(spec3.card_id) is None

    # user3 adds a message, user2 views it, should remove user2's card
    message1 = chat_message_manager.add_chat_message(str(uuid.uuid4()), 't', chat.id, user3.id)
    chat_message_manager.record_views([message1.id], user2.id)
    assert card_manager.get_card(spec2.card_id) is None
