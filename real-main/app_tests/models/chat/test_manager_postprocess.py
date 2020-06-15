import logging
from uuid import uuid4

import pendulum
import pytest

from app.models.card.specs import ChatCardSpec


@pytest.fixture
def user1(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user1


@pytest.fixture
def chat(chat_manager, user1, user2):
    yield chat_manager.add_direct_chat('cid', user1.id, user2.id)


@pytest.fixture
def message1(chat_message_manager, chat, user1):
    yield chat_message_manager.add_chat_message(str(uuid4()), 'lore ipsum', chat.id, user1.id)


@pytest.fixture
def message2(chat_message_manager, chat, user2):
    yield chat_message_manager.add_chat_message(str(uuid4()), 'lore ipsum', chat.id, user2.id)


def test_postprocess_chat_message_added(chat_manager, card_manager, chat, user1, user2, caplog):
    spec1 = ChatCardSpec(user1.id)
    spec2 = ChatCardSpec(user2.id)

    # verify starting state
    chat.refresh_item()
    assert 'messageCount' not in chat.item
    assert 'lastMessageActivityAt' not in chat.item
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', chat.item['createdAt']]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', chat.item['createdAt']]
    assert 'unviewedMessageCount' not in user1_member_item
    assert 'unviewedMessageCount' not in user2_member_item
    assert card_manager.get_card(spec1.card_id) is None
    assert card_manager.get_card(spec2.card_id) is None

    # postprocess adding a message by user1, verify state
    now = pendulum.now('utc')
    chat_manager.postprocess_chat_message_added(chat.id, user1.id, now)
    chat.refresh_item()
    assert chat.item['messageCount'] == 1
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert 'unviewedMessageCount' not in user1_member_item
    assert user2_member_item['unviewedMessageCount'] == 1
    assert card_manager.get_card(spec1.card_id) is None
    assert card_manager.get_card(spec2.card_id)

    # postprocess adding a message by user2, verify state
    now = pendulum.now('utc')
    chat_manager.postprocess_chat_message_added(chat.id, user2.id, now)
    chat.refresh_item()
    assert chat.item['messageCount'] == 2
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user1_member_item['unviewedMessageCount'] == 1
    assert user2_member_item['unviewedMessageCount'] == 1
    assert card_manager.get_card(spec1.card_id)
    assert card_manager.get_card(spec2.card_id)

    # postprocess adding a another message by user2 out of order
    before = pendulum.now('utc').subtract(seconds=5)
    with caplog.at_level(logging.WARNING):
        chat_manager.postprocess_chat_message_added(chat.id, user2.id, before)
    assert len(caplog.records) == 3
    assert all('Failed' in rec.msg for rec in caplog.records)
    assert all('last message activity' in rec.msg for rec in caplog.records)
    assert all(chat.id in rec.msg for rec in caplog.records)
    assert user1.id in caplog.records[1].msg
    assert user2.id in caplog.records[2].msg

    # verify final state
    chat.refresh_item()
    assert chat.item['messageCount'] == 3
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user1_member_item['unviewedMessageCount'] == 2
    assert user2_member_item['unviewedMessageCount'] == 1
    assert card_manager.get_card(spec1.card_id)
    assert card_manager.get_card(spec2.card_id)


def test_postprocess_system_chat_message_added(chat_manager, chat_message_manager, card_manager, chat, user1, user2):
    spec1 = ChatCardSpec(user1.id)
    spec2 = ChatCardSpec(user2.id)

    # verify starting state
    chat.refresh_item()
    assert 'messageCount' not in chat.item
    assert 'lastMessageActivityAt' not in chat.item
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', chat.item['createdAt']]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', chat.item['createdAt']]
    assert 'unviewedMessageCount' not in user1_member_item
    assert 'unviewedMessageCount' not in user2_member_item
    assert card_manager.get_card(spec1.card_id) is None
    assert card_manager.get_card(spec2.card_id) is None

    # postprocess adding a message by the system, verify state
    now = pendulum.now('utc')
    chat_manager.postprocess_chat_message_added(chat.id, None, now)
    chat.refresh_item()
    assert chat.item['messageCount'] == 1
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user1_member_item['unviewedMessageCount'] == 1
    assert user2_member_item['unviewedMessageCount'] == 1
    assert card_manager.get_card(spec1.card_id)
    assert card_manager.get_card(spec2.card_id)


def test_postprocess_chat_message_deleted(
    chat_manager, card_manager, chat, user1, user2, caplog, message1, message2
):
    # postprocess adding two messages by user1, user2 views one of them
    created_at1 = pendulum.parse(message1.item['createdAt'])
    created_at2 = pendulum.parse(message2.item['createdAt'])
    assert created_at2 > created_at1
    chat_manager.postprocess_chat_message_added(chat.id, user1.id, created_at1)
    chat_manager.postprocess_chat_message_added(chat.id, user1.id, created_at2)
    message2.view_dynamo.add_view(message2.id, user2.id, 1, pendulum.now('utc'))
    chat_manager.postprocess_chat_message_view_added(chat.id, user2.id)

    # verify starting state
    chat.refresh_item()
    assert chat.item['messageCount'] == 2
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == created_at2
    assert 'unviewedMessageCount' not in chat.member_dynamo.get(chat.id, user1.id)
    assert chat.member_dynamo.get(chat.id, user2.id)['unviewedMessageCount'] == 1

    # postprocess deleting the message user2 viewed, verify state
    chat_manager.postprocess_chat_message_deleted(chat.id, message2.id, user1.id)
    chat.refresh_item()
    assert chat.item['messageCount'] == 1
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == created_at2
    assert 'unviewedMessageCount' not in chat.member_dynamo.get(chat.id, user1.id)
    assert chat.member_dynamo.get(chat.id, user2.id)['unviewedMessageCount'] == 1

    # postprocess deleting the message user2 did not view, verify state
    chat_manager.postprocess_chat_message_deleted(chat.id, message1.id, user1.id)
    chat.refresh_item()
    assert chat.item['messageCount'] == 0
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == created_at2
    assert 'unviewedMessageCount' not in chat.member_dynamo.get(chat.id, user1.id)
    assert chat.member_dynamo.get(chat.id, user2.id)['unviewedMessageCount'] == 0


def test_postprocess_chat_message_view_added(chat_manager, card_manager, chat, user1, user2, caplog):
    # postprocess adding one message by user1, verify state
    now = pendulum.now('utc')
    chat_manager.postprocess_chat_message_added(chat.id, user1.id, now)
    chat.refresh_item()
    assert chat.item['messageCount'] == 1
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    assert 'unviewedMessageCount' not in chat.member_dynamo.get(chat.id, user1.id)
    assert chat.member_dynamo.get(chat.id, user2.id)['unviewedMessageCount'] == 1

    # postprocess adding a view, verify state
    chat_manager.postprocess_chat_message_view_added(chat.id, user2.id)
    chat.refresh_item()
    assert chat.item['messageCount'] == 1
    assert 'unviewedMessageCount' not in chat.member_dynamo.get(chat.id, user1.id)
    assert chat.member_dynamo.get(chat.id, user2.id)['unviewedMessageCount'] == 0
