from operator import itemgetter
from unittest.mock import Mock, call
from uuid import uuid4

import pytest


@pytest.fixture
def chat_postprocessor(chat_manager):
    yield chat_manager.postprocessor


@pytest.fixture
def user1(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user1


@pytest.fixture
def chat(chat_manager, user1, user2):
    yield chat_manager.add_direct_chat('cid', user1.id, user2.id)


def test_run_member_added(chat_postprocessor, chat, user1):
    pk, sk = itemgetter('partitionKey', 'sortKey')(chat.member_dynamo.pk(chat.id, user1.id))
    old_item = {}

    # simulate adding member with no unviewed message count
    new_item = chat.member_dynamo.get(chat.id, user1.id)
    assert 'messagesUnviewedCount' not in new_item

    # postprocess that, verify calls
    chat_postprocessor.user_manager = Mock(chat_postprocessor.user_manager)
    chat_postprocessor.run(pk, sk, old_item, new_item)
    assert chat_postprocessor.user_manager.mock_calls == []

    # simulate adding member with some unviewed message count
    new_item = chat.member_dynamo.increment_messages_unviewed_count(chat.id, user1.id)
    assert new_item['messagesUnviewedCount'] == 1

    # postprocess that, verify calls
    chat_postprocessor.user_manager = Mock(chat_postprocessor.user_manager)
    chat_postprocessor.run(pk, sk, old_item, new_item)
    assert chat_postprocessor.user_manager.mock_calls == [
        call.dynamo.increment_chats_with_unviewed_messages_count(user1.id),
    ]

    # simulate adding member with zero unviewed message count
    new_item = chat.member_dynamo.decrement_messages_unviewed_count(chat.id, user1.id)
    assert new_item['messagesUnviewedCount'] == 0

    # postprocess that, verify calls
    chat_postprocessor.user_manager = Mock(chat_postprocessor.user_manager)
    chat_postprocessor.run(pk, sk, old_item, new_item)
    assert chat_postprocessor.user_manager.mock_calls == []


def test_run_member_edited(chat_postprocessor, chat, user1):
    pk, sk = itemgetter('partitionKey', 'sortKey')(chat.member_dynamo.pk(chat.id, user1.id))

    # simulate editing member from no unviewed message count to some, verify
    old_item = chat.member_dynamo.get(chat.id, user1.id)
    new_item = chat.member_dynamo.increment_messages_unviewed_count(chat.id, user1.id)
    assert 'messagesUnviewedCount' not in old_item
    assert new_item['messagesUnviewedCount'] == 1

    # postprocess that, verify calls
    chat_postprocessor.user_manager = Mock(chat_postprocessor.user_manager)
    chat_postprocessor.run(pk, sk, old_item, new_item)
    assert chat_postprocessor.user_manager.mock_calls == [
        call.dynamo.increment_chats_with_unviewed_messages_count(user1.id),
    ]

    # simulate editing member from some unviewed message count to none, verify
    old_item = new_item
    new_item = chat.member_dynamo.decrement_messages_unviewed_count(chat.id, user1.id)
    assert old_item['messagesUnviewedCount'] == 1
    assert new_item['messagesUnviewedCount'] == 0

    # postprocess that, verify calls
    chat_postprocessor.user_manager = Mock(chat_postprocessor.user_manager)
    chat_postprocessor.run(pk, sk, old_item, new_item)
    assert chat_postprocessor.user_manager.mock_calls == [
        call.dynamo.decrement_chats_with_unviewed_messages_count(user1.id, fail_soft=True),
    ]

    # simulate editing member from zero unviewed message count to some, verify
    old_item = new_item
    new_item = chat.member_dynamo.increment_messages_unviewed_count(chat.id, user1.id)
    assert old_item['messagesUnviewedCount'] == 0
    assert new_item['messagesUnviewedCount'] == 1

    # postprocess that, verify calls
    chat_postprocessor.user_manager = Mock(chat_postprocessor.user_manager)
    chat_postprocessor.run(pk, sk, old_item, new_item)
    assert chat_postprocessor.user_manager.mock_calls == [
        call.dynamo.increment_chats_with_unviewed_messages_count(user1.id),
    ]


def test_run_member_deleted(chat_postprocessor, chat, user1):
    pk, sk = itemgetter('partitionKey', 'sortKey')(chat.member_dynamo.pk(chat.id, user1.id))
    new_item = {}

    # simulate deleting member with no unviewed message count
    old_item = chat.member_dynamo.get(chat.id, user1.id)
    assert 'messagesUnviewedCount' not in old_item

    # postprocess that, verify calls
    chat_postprocessor.user_manager = Mock(chat_postprocessor.user_manager)
    chat_postprocessor.run(pk, sk, old_item, new_item)
    assert chat_postprocessor.user_manager.mock_calls == []

    # simulate deleting member with some unviewed message count
    old_item = chat.member_dynamo.increment_messages_unviewed_count(chat.id, user1.id)
    assert old_item['messagesUnviewedCount'] == 1

    # postprocess that, verify calls
    chat_postprocessor.user_manager = Mock(chat_postprocessor.user_manager)
    chat_postprocessor.run(pk, sk, old_item, new_item)
    assert chat_postprocessor.user_manager.mock_calls == [
        call.dynamo.decrement_chats_with_unviewed_messages_count(user1.id, fail_soft=True),
    ]

    # simulate deleting member with a zero unviewed message count
    old_item = chat.member_dynamo.decrement_messages_unviewed_count(chat.id, user1.id)
    assert old_item['messagesUnviewedCount'] == 0

    # postprocess that, verify calls
    chat_postprocessor.user_manager = Mock(chat_postprocessor.user_manager)
    chat_postprocessor.run(pk, sk, old_item, new_item)
    assert chat_postprocessor.user_manager.mock_calls == []
