import logging
from unittest.mock import Mock, call
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


def test_postprocess_record_member_added(chat_manager, chat, user1):
    typed_pk = chat.member_dynamo.typed_pk(chat.id, user1.id)
    pk, sk = typed_pk['partitionKey']['S'], typed_pk['sortKey']['S']
    old_item = None

    # simulate adding member with no unviewed message count
    new_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    assert 'messagesUnviewedCount' not in new_item

    # postprocess that, verify calls
    chat_manager.user_manager = Mock(chat_manager.user_manager)
    chat_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat_manager.user_manager.mock_calls == []

    # simulate adding member with some unviewed message count
    chat.member_dynamo.increment_messages_unviewed_count(chat.id, user1.id)
    new_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    assert new_item['messagesUnviewedCount']['N'] == '1'

    # postprocess that, verify calls
    chat_manager.user_manager = Mock(chat_manager.user_manager)
    chat_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat_manager.user_manager.mock_calls == [
        call.dynamo.increment_chats_with_unviewed_messages_count(user1.id),
    ]

    # simulate adding member with zero unviewed message count
    chat.member_dynamo.decrement_messages_unviewed_count(chat.id, user1.id)
    new_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    assert new_item['messagesUnviewedCount']['N'] == '0'

    # postprocess that, verify calls
    chat_manager.user_manager = Mock(chat_manager.user_manager)
    chat_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat_manager.user_manager.mock_calls == []


def test_postprocess_record_member_edited(chat_manager, chat, user1):
    typed_pk = chat.member_dynamo.typed_pk(chat.id, user1.id)
    pk, sk = typed_pk['partitionKey']['S'], typed_pk['sortKey']['S']

    # simulate editing member from no unviewed message count to some, verify
    old_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    chat.member_dynamo.increment_messages_unviewed_count(chat.id, user1.id)
    new_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    assert 'messagesUnviewedCount' not in old_item
    assert new_item['messagesUnviewedCount']['N'] == '1'

    # postprocess that, verify calls
    chat_manager.user_manager = Mock(chat_manager.user_manager)
    chat_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat_manager.user_manager.mock_calls == [
        call.dynamo.increment_chats_with_unviewed_messages_count(user1.id),
    ]

    # simulate editing member from some unviewed message count to none, verify
    old_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    chat.member_dynamo.decrement_messages_unviewed_count(chat.id, user1.id)
    new_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    assert old_item['messagesUnviewedCount']['N'] == '1'
    assert new_item['messagesUnviewedCount']['N'] == '0'

    # postprocess that, verify calls
    chat_manager.user_manager = Mock(chat_manager.user_manager)
    chat_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat_manager.user_manager.mock_calls == [
        call.dynamo.decrement_chats_with_unviewed_messages_count(user1.id, fail_soft=True),
    ]

    # simulate editing member from zero unviewed message count to some, verify
    old_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    chat.member_dynamo.increment_messages_unviewed_count(chat.id, user1.id)
    new_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    assert old_item['messagesUnviewedCount']['N'] == '0'
    assert new_item['messagesUnviewedCount']['N'] == '1'

    # postprocess that, verify calls
    chat_manager.user_manager = Mock(chat_manager.user_manager)
    chat_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat_manager.user_manager.mock_calls == [
        call.dynamo.increment_chats_with_unviewed_messages_count(user1.id),
    ]


def test_postprocess_record_member_deleted(chat_manager, chat, user1):
    typed_pk = chat.member_dynamo.typed_pk(chat.id, user1.id)
    pk, sk = typed_pk['partitionKey']['S'], typed_pk['sortKey']['S']
    new_item = None

    # simulate deleting member with no unviewed message count
    old_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    assert 'messagesUnviewedCount' not in old_item

    # postprocess that, verify calls
    chat_manager.user_manager = Mock(chat_manager.user_manager)
    chat_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat_manager.user_manager.mock_calls == []

    # simulate deleting member with some unviewed message count
    chat.member_dynamo.increment_messages_unviewed_count(chat.id, user1.id)
    old_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    assert old_item['messagesUnviewedCount']['N'] == '1'

    # postprocess that, verify calls
    chat_manager.user_manager = Mock(chat_manager.user_manager)
    chat_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat_manager.user_manager.mock_calls == [
        call.dynamo.decrement_chats_with_unviewed_messages_count(user1.id, fail_soft=True),
    ]

    # simulate deleting member with a zero unviewed message count
    chat.member_dynamo.decrement_messages_unviewed_count(chat.id, user1.id)
    old_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    assert old_item['messagesUnviewedCount']['N'] == '0'

    # postprocess that, verify calls
    chat_manager.user_manager = Mock(chat_manager.user_manager)
    chat_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat_manager.user_manager.mock_calls == []


def test_postprocess_record_view_added_edited_deleted(chat_manager, card_manager, chat, user1):
    card_spec = ChatCardSpec(user1.id)

    typed_pk = chat.view_dynamo.typed_pk(chat.id, user1.id)
    pk, sk = typed_pk['partitionKey']['S'], typed_pk['sortKey']['S']
    old_item = None

    # simulate a new view
    chat.record_view_count(user1.id, 2)
    new_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    assert new_item['viewCount']['N'] == '2'
    old_item = None

    # set up the card
    card_manager.add_card_by_spec_if_dne(card_spec)
    assert card_manager.get_card(card_spec.card_id)

    # set up the messagesUnviewedCount so it can be cleared
    chat.member_dynamo.increment_messages_unviewed_count(chat.id, user1.id)
    assert chat.member_dynamo.get(chat.id, user1.id)['messagesUnviewedCount'] == 1

    # postprocess the add, verify state changed
    chat_manager.postprocess_record(pk, sk, old_item, new_item)
    assert 'messagesUnviewedCount' not in chat.member_dynamo.get(chat.id, user1.id)
    assert card_manager.get_card(card_spec.card_id) is None

    # simulate recording another view on a chat that's already been viewed
    old_item = new_item
    chat.record_view_count(user1.id, 3)
    new_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    assert new_item['viewCount']['N'] == '5'

    # set up the card again
    card_manager.add_card_by_spec_if_dne(card_spec)
    assert card_manager.get_card(card_spec.card_id)

    # set up the messagesUnviewedCount so it can be cleared
    chat.member_dynamo.increment_messages_unviewed_count(chat.id, user1.id)
    assert chat.member_dynamo.get(chat.id, user1.id)['messagesUnviewedCount'] == 1

    # postprocess the edit, verify state changed
    chat_manager.postprocess_record(pk, sk, old_item, new_item)
    assert 'messagesUnviewedCount' not in chat.member_dynamo.get(chat.id, user1.id)
    assert card_manager.get_card(card_spec.card_id) is None

    # simulate deleting the view record altogether
    old_item = new_item
    new_item = None

    # set up the card again
    card_manager.add_card_by_spec_if_dne(card_spec)
    assert card_manager.get_card(card_spec.card_id)

    # set up the messagesUnviewedCount so it can be cleared
    chat.member_dynamo.increment_messages_unviewed_count(chat.id, user1.id)
    assert chat.member_dynamo.get(chat.id, user1.id)['messagesUnviewedCount'] == 1

    # postprocess the delete, verify state did not change
    chat_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat.member_dynamo.get(chat.id, user1.id)['messagesUnviewedCount'] == 1
    assert card_manager.get_card(card_spec.card_id)


def test_postprocess_record_view_edited(chat_manager, chat, user1):
    typed_pk = chat.member_dynamo.typed_pk(chat.id, user1.id)
    pk, sk = typed_pk['partitionKey']['S'], typed_pk['sortKey']['S']

    # simulate editing member from no unviewed message count to some, verify
    old_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    chat.member_dynamo.increment_messages_unviewed_count(chat.id, user1.id)
    new_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    assert 'messagesUnviewedCount' not in old_item
    assert new_item['messagesUnviewedCount']['N'] == '1'

    # postprocess that, verify calls
    chat_manager.user_manager = Mock(chat_manager.user_manager)
    chat_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat_manager.user_manager.mock_calls == [
        call.dynamo.increment_chats_with_unviewed_messages_count(user1.id),
    ]

    # simulate editing member from some unviewed message count to none, verify
    old_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    chat.member_dynamo.decrement_messages_unviewed_count(chat.id, user1.id)
    new_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    assert old_item['messagesUnviewedCount']['N'] == '1'
    assert new_item['messagesUnviewedCount']['N'] == '0'

    # postprocess that, verify calls
    chat_manager.user_manager = Mock(chat_manager.user_manager)
    chat_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat_manager.user_manager.mock_calls == [
        call.dynamo.decrement_chats_with_unviewed_messages_count(user1.id, fail_soft=True),
    ]

    # simulate editing member from zero unviewed message count to some, verify
    old_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    chat.member_dynamo.increment_messages_unviewed_count(chat.id, user1.id)
    new_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    assert old_item['messagesUnviewedCount']['N'] == '0'
    assert new_item['messagesUnviewedCount']['N'] == '1'

    # postprocess that, verify calls
    chat_manager.user_manager = Mock(chat_manager.user_manager)
    chat_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat_manager.user_manager.mock_calls == [
        call.dynamo.increment_chats_with_unviewed_messages_count(user1.id),
    ]


def test_postprocess_record_view_deleted(chat_manager, chat, user1):
    typed_pk = chat.member_dynamo.typed_pk(chat.id, user1.id)
    pk, sk = typed_pk['partitionKey']['S'], typed_pk['sortKey']['S']
    new_item = None

    # simulate deleting member with no unviewed message count
    old_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    assert 'messagesUnviewedCount' not in old_item

    # postprocess that, verify calls
    chat_manager.user_manager = Mock(chat_manager.user_manager)
    chat_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat_manager.user_manager.mock_calls == []

    # simulate deleting member with some unviewed message count
    chat.member_dynamo.increment_messages_unviewed_count(chat.id, user1.id)
    old_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    assert old_item['messagesUnviewedCount']['N'] == '1'

    # postprocess that, verify calls
    chat_manager.user_manager = Mock(chat_manager.user_manager)
    chat_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat_manager.user_manager.mock_calls == [
        call.dynamo.decrement_chats_with_unviewed_messages_count(user1.id, fail_soft=True),
    ]

    # simulate deleting member with a zero unviewed message count
    chat.member_dynamo.decrement_messages_unviewed_count(chat.id, user1.id)
    old_item = chat.member_dynamo.client.get_typed_item(typed_pk)
    assert old_item['messagesUnviewedCount']['N'] == '0'

    # postprocess that, verify calls
    chat_manager.user_manager = Mock(chat_manager.user_manager)
    chat_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat_manager.user_manager.mock_calls == []


def test_postprocess_chat_message_added(chat_manager, card_manager, chat, user1, user2, caplog):
    spec1 = ChatCardSpec(user1.id)
    spec2 = ChatCardSpec(user2.id)

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
    assert card_manager.get_card(spec1.card_id) is None
    assert card_manager.get_card(spec2.card_id) is None

    # postprocess adding a message by user1, verify state
    now = pendulum.now('utc')
    chat_manager.postprocess_chat_message_added(chat.id, user1.id, now)
    chat.refresh_item()
    assert chat.item['messagesCount'] == 1
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert 'messagesUnviewedCount' not in user1_member_item
    assert user2_member_item['messagesUnviewedCount'] == 1
    assert card_manager.get_card(spec1.card_id) is None
    assert card_manager.get_card(spec2.card_id)

    # postprocess adding a message by user2, verify state
    now = pendulum.now('utc')
    chat_manager.postprocess_chat_message_added(chat.id, user2.id, now)
    chat.refresh_item()
    assert chat.item['messagesCount'] == 2
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user1_member_item['messagesUnviewedCount'] == 1
    assert user2_member_item['messagesUnviewedCount'] == 1
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
    assert chat.item['messagesCount'] == 3
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user1_member_item['messagesUnviewedCount'] == 2
    assert user2_member_item['messagesUnviewedCount'] == 1
    assert card_manager.get_card(spec1.card_id)
    assert card_manager.get_card(spec2.card_id)


def test_postprocess_system_chat_message_added(chat_manager, chat_message_manager, card_manager, chat, user1, user2):
    spec1 = ChatCardSpec(user1.id)
    spec2 = ChatCardSpec(user2.id)

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
    assert card_manager.get_card(spec1.card_id) is None
    assert card_manager.get_card(spec2.card_id) is None

    # postprocess adding a message by the system, verify state
    now = pendulum.now('utc')
    chat_manager.postprocess_chat_message_added(chat.id, None, now)
    chat.refresh_item()
    assert chat.item['messagesCount'] == 1
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user1_member_item['messagesUnviewedCount'] == 1
    assert user2_member_item['messagesUnviewedCount'] == 1
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
    assert chat.item['messagesCount'] == 2
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == created_at2
    assert 'messagesUnviewedCount' not in chat.member_dynamo.get(chat.id, user1.id)
    assert chat.member_dynamo.get(chat.id, user2.id)['messagesUnviewedCount'] == 1

    # postprocess deleting the message user2 viewed, verify state
    chat_manager.postprocess_chat_message_deleted(chat.id, message2.id, user1.id)
    chat.refresh_item()
    assert chat.item['messagesCount'] == 1
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == created_at2
    assert 'messagesUnviewedCount' not in chat.member_dynamo.get(chat.id, user1.id)
    assert chat.member_dynamo.get(chat.id, user2.id)['messagesUnviewedCount'] == 1

    # postprocess deleting the message user2 did not view, verify state
    chat_manager.postprocess_chat_message_deleted(chat.id, message1.id, user1.id)
    chat.refresh_item()
    assert chat.item['messagesCount'] == 0
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == created_at2
    assert 'messagesUnviewedCount' not in chat.member_dynamo.get(chat.id, user1.id)
    assert chat.member_dynamo.get(chat.id, user2.id)['messagesUnviewedCount'] == 0


def test_postprocess_chat_message_view_added(chat_manager, card_manager, chat, user1, user2, caplog):
    # postprocess adding one message by user1, verify state
    now = pendulum.now('utc')
    chat_manager.postprocess_chat_message_added(chat.id, user1.id, now)
    chat.refresh_item()
    assert chat.item['messagesCount'] == 1
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    assert 'messagesUnviewedCount' not in chat.member_dynamo.get(chat.id, user1.id)
    assert chat.member_dynamo.get(chat.id, user2.id)['messagesUnviewedCount'] == 1

    # postprocess adding a view, verify state
    chat_manager.postprocess_chat_message_view_added(chat.id, user2.id)
    chat.refresh_item()
    assert chat.item['messagesCount'] == 1
    assert 'messagesUnviewedCount' not in chat.member_dynamo.get(chat.id, user1.id)
    assert chat.member_dynamo.get(chat.id, user2.id)['messagesUnviewedCount'] == 0
