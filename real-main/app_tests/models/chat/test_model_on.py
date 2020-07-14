import logging
from uuid import uuid4

import pendulum
import pytest


@pytest.fixture
def user1(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user1


@pytest.fixture
def chat(chat_manager, user1, user2):
    yield chat_manager.add_direct_chat(str(uuid4()), user1.id, user2.id)


@pytest.fixture
def user1_message(chat_message_manager, chat, user1):
    yield chat_message_manager.add_chat_message(str(uuid4()), 'lore', chat.id, user1.id)


@pytest.fixture
def user2_message(chat_message_manager, chat, user2):
    yield chat_message_manager.add_chat_message(str(uuid4()), 'lore', chat.id, user2.id)


@pytest.fixture
def system_message(chat_message_manager, chat):
    yield chat_message_manager.add_system_message(chat.id, 'system lore')


def test_on_message_added(chat, user1, user2, caplog, user1_message, user2_message):
    # verify starting state
    chat.refresh_item()
    assert 'messagesCount' not in chat.item
    assert 'lastMessageActivityAt' not in chat.item
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', chat.item['createdAt']]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', chat.item['createdAt']]
    assert 'messagesUnviewedCount' not in user1_member_item
    assert 'messagesUnviewedCount' not in user2_member_item

    # postprocess adding a message by user1, verify state
    now = user1_message.created_at
    chat.on_message_add(user1_message)
    chat.refresh_item()
    assert chat.item['messagesCount'] == 1
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert 'messagesUnviewedCount' not in user1_member_item
    assert user2_member_item['messagesUnviewedCount'] == 1

    # postprocess adding a message by user2, verify state
    now = user2_message.created_at
    chat.on_message_add(user2_message)
    chat.refresh_item()
    assert chat.item['messagesCount'] == 2
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user1_member_item['messagesUnviewedCount'] == 1
    assert user2_member_item['messagesUnviewedCount'] == 1

    # postprocess adding a another message by user2 out of order
    user2_message.created_at = user2_message.created_at.subtract(seconds=5)
    with caplog.at_level(logging.WARNING):
        chat.on_message_add(user2_message)
    assert len(caplog.records) == 3
    assert all('Failed' in rec.msg for rec in caplog.records)
    assert all('last message activity' in rec.msg for rec in caplog.records)
    assert all(chat.id in rec.msg for rec in caplog.records)
    assert user1.id in caplog.records[1].msg
    assert user2.id in caplog.records[2].msg

    # verify final state
    chat.refresh_item()
    assert chat.item['messagesCount'] == 3
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user1_member_item['messagesUnviewedCount'] == 2
    assert user2_member_item['messagesUnviewedCount'] == 1


def test_on_message_added_system_message(chat, user1, user2, system_message):
    # verify starting state
    chat.refresh_item()
    assert 'messagesCount' not in chat.item
    assert 'lastMessageActivityAt' not in chat.item
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', chat.item['createdAt']]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', chat.item['createdAt']]
    assert 'messagesUnviewedCount' not in user1_member_item
    assert 'messagesUnviewedCount' not in user2_member_item

    # postprocess adding a message by the system, verify state
    now = system_message.created_at
    chat.on_message_add(system_message)
    chat.refresh_item()
    assert chat.item['messagesCount'] == 1
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user1_member_item['messagesUnviewedCount'] == 1
    assert user2_member_item['messagesUnviewedCount'] == 1


def test_on_message_deleted(chat, user1, user2, caplog, user1_message):
    # postprocess an add to increment counts, and verify starting state
    chat.on_message_add(user1_message)
    assert chat.refresh_item().item['messagesCount'] == 1
    assert chat.member_dynamo.get(chat.id, user1.id).get('messagesUnviewedCount', 0) == 0
    assert chat.member_dynamo.get(chat.id, user2.id).get('messagesUnviewedCount', 0) == 1

    # postprocess a deleted message, verify counts drop as expected
    chat.on_message_delete(user1_message)
    assert chat.refresh_item().item['messagesCount'] == 0
    assert chat.member_dynamo.get(chat.id, user1.id).get('messagesUnviewedCount', 0) == 0
    assert chat.member_dynamo.get(chat.id, user2.id).get('messagesUnviewedCount', 0) == 0

    # postprocess a deleted message, verify fails softly and final state
    with caplog.at_level(logging.WARNING):
        chat.on_message_delete(user1_message)
    assert len(caplog.records) == 2
    assert 'Failed to decrement messagesCount' in caplog.records[0].msg
    assert 'Failed to decrement messagesUnviewedCount' in caplog.records[1].msg
    assert chat.id in caplog.records[0].msg
    assert chat.id in caplog.records[1].msg
    assert chat.refresh_item().item['messagesCount'] == 0
    assert chat.member_dynamo.get(chat.id, user1.id).get('messagesUnviewedCount', 0) == 0
    assert chat.member_dynamo.get(chat.id, user2.id).get('messagesUnviewedCount', 0) == 0


def test_on_message_delete_handles_chat_views_correctly(chat, user1, user2, chat_message_manager, chat_manager):
    # each user posts two messages, one of which is 'viewed' by both and the other is not
    message1 = chat_message_manager.add_chat_message(str(uuid4()), 'lore ipsum', chat.id, user1.id)
    message2 = chat_message_manager.add_chat_message(str(uuid4()), 'lore ipsum', chat.id, user2.id)
    chat.on_message_add(message1)
    chat.on_message_add(message2)

    chat_manager.record_views([chat.id], user1.id)
    chat_manager.record_views([chat.id], user2.id)
    chat_manager.member_dynamo.clear_messages_unviewed_count(chat.id, user1.id)  # postprocess
    chat_manager.member_dynamo.clear_messages_unviewed_count(chat.id, user2.id)  # postprocess

    message3 = chat_message_manager.add_chat_message(str(uuid4()), 'lore ipsum', chat.id, user1.id)
    message4 = chat_message_manager.add_chat_message(str(uuid4()), 'lore ipsum', chat.id, user2.id)
    chat.on_message_add(message3)
    chat.on_message_add(message4)

    # verify starting state
    chat.refresh_item()
    assert chat.item['messagesCount'] == 4
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == message4.created_at
    assert chat.member_dynamo.get(chat.id, user1.id)['messagesUnviewedCount'] == 1
    assert chat.member_dynamo.get(chat.id, user2.id)['messagesUnviewedCount'] == 1

    # postprocess deleting message2, check counts
    chat.on_message_delete(message2)
    assert chat.refresh_item().item['messagesCount'] == 3
    assert chat.member_dynamo.get(chat.id, user1.id)['messagesUnviewedCount'] == 1
    assert chat.member_dynamo.get(chat.id, user2.id)['messagesUnviewedCount'] == 1

    # postprocess deleting message3, check counts
    chat.on_message_delete(message3)
    assert chat.refresh_item().item['messagesCount'] == 2
    assert chat.member_dynamo.get(chat.id, user1.id)['messagesUnviewedCount'] == 1
    assert chat.member_dynamo.get(chat.id, user2.id)['messagesUnviewedCount'] == 0

    # postprocess deleting message1, check counts
    chat.on_message_delete(message1)
    assert chat.refresh_item().item['messagesCount'] == 1
    assert chat.member_dynamo.get(chat.id, user1.id)['messagesUnviewedCount'] == 1
    assert chat.member_dynamo.get(chat.id, user2.id)['messagesUnviewedCount'] == 0

    # postprocess deleting message4, check counts
    chat.on_message_delete(message4)
    assert chat.refresh_item().item['messagesCount'] == 0
    assert chat.member_dynamo.get(chat.id, user1.id)['messagesUnviewedCount'] == 0
    assert chat.member_dynamo.get(chat.id, user2.id)['messagesUnviewedCount'] == 0
