import logging
from unittest.mock import Mock, call
from uuid import uuid4

import pendulum
import pytest


@pytest.fixture
def chat_message_postprocessor(chat_message_manager):
    yield chat_message_manager.postprocessor


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
def message(chat_message_manager, chat, user1):
    yield chat_message_manager.add_chat_message(str(uuid4()), 'lore ipsum', chat.id, user1.id)


@pytest.fixture
def system_message(chat_message_manager, chat):
    yield chat_message_manager.add_system_message(chat.id, 'lore ipsum')


def test_run_chat_message_added(chat_message_postprocessor, message):
    pk, sk = message.item['partitionKey'], message.item['sortKey']
    created_at = pendulum.parse(message.item['createdAt'])

    # postprocess the user message, verify calls correct
    chat_message_postprocessor.chat_manager = Mock(chat_message_postprocessor.chat_manager)
    chat_message_postprocessor.run(pk, sk, {}, message.item)
    assert chat_message_postprocessor.chat_manager.mock_calls == [
        call.postprocessor.chat_message_added(message.chat_id, message.user_id, created_at),
    ]


def test_run_system_chat_message_added(chat_message_postprocessor, system_message):
    pk, sk = system_message.item['partitionKey'], system_message.item['sortKey']
    created_at = pendulum.parse(system_message.item['createdAt'])

    # postprocess the user message, verify calls correct
    chat_message_postprocessor.chat_manager = Mock(chat_message_postprocessor.chat_manager)
    chat_message_postprocessor.run(pk, sk, {}, system_message.item)
    assert chat_message_postprocessor.chat_manager.mock_calls == [
        call.postprocessor.chat_message_added(system_message.chat_id, None, created_at),
    ]


def test_run_chat_message_deleted(chat_message_postprocessor, message):
    pk, sk = message.item['partitionKey'], message.item['sortKey']
    created_at = pendulum.parse(message.item['createdAt'])

    # postprocess the user message, verify calls correct
    chat_message_postprocessor.chat_manager = Mock(chat_message_postprocessor.chat_manager)
    chat_message_postprocessor.run(pk, sk, message.item, {})
    assert chat_message_postprocessor.chat_manager.mock_calls == [
        call.postprocessor.chat_message_deleted(message.chat_id, message.id, message.user_id, created_at),
    ]


def test_run_chat_message_view_added(chat_message_postprocessor, message, user2):
    # create a view by user2
    message.view_dynamo.add_view(message.id, user2.id, 1, pendulum.now('utc'))
    view_item = message.view_dynamo.get_view(message.id, user2.id)
    pk, sk = view_item['partitionKey'], view_item['sortKey']

    # postprocess adding that message view, verify calls correct
    chat_message_postprocessor.chat_manager = Mock(chat_message_postprocessor.chat_manager)
    chat_message_postprocessor.run(pk, sk, {}, view_item)
    assert chat_message_postprocessor.chat_manager.mock_calls == [
        call.postprocessor.chat_message_view_added(message.chat_id, user2.id),
    ]


def test_run_chat_message_flag(chat_message_postprocessor, message, user2):
    # create a flag by user2
    message.flag_dynamo.add(message.id, user2.id)
    flag_item = message.flag_dynamo.get(message.id, user2.id)
    pk, sk = flag_item['partitionKey'], flag_item['sortKey']

    # set up mocks
    chat_message_postprocessor.message_flag_added = Mock()
    chat_message_postprocessor.message_flag_deleted = Mock()

    # postprocess adding that message flag, verify calls correct
    chat_message_postprocessor.run(pk, sk, {}, flag_item)
    assert chat_message_postprocessor.message_flag_added.mock_calls == [call(message.id, user2.id)]
    assert chat_message_postprocessor.message_flag_deleted.mock_calls == []

    # reset mocks
    chat_message_postprocessor.message_flag_added = Mock()
    chat_message_postprocessor.message_flag_deleted = Mock()

    # postprocess editing that message flag, verify calls correct
    chat_message_postprocessor.run(pk, sk, flag_item, flag_item)
    assert chat_message_postprocessor.message_flag_added.mock_calls == []
    assert chat_message_postprocessor.message_flag_deleted.mock_calls == []

    # postprocess deleting that message flag, verify calls correct
    chat_message_postprocessor.run(pk, sk, flag_item, {})
    assert chat_message_postprocessor.message_flag_added.mock_calls == []
    assert chat_message_postprocessor.message_flag_deleted.mock_calls == [call(message.id)]


def test_chat_message_flag_added(chat_message_postprocessor, message, user2):
    # check starting state
    assert message.refresh_item().item.get('flagCount', 0) == 0

    # messageprocess, verify flagCount is incremented & not force achived
    chat_message_postprocessor.message_flag_added(message.id, user2.id)
    assert message.refresh_item().item.get('flagCount', 0) == 1


def test_chat_message_flag_deleted(chat_message_postprocessor, message, user2, caplog):
    # configure and check starting state
    chat_message_postprocessor.message_flag_added(message.id, user2.id)
    assert message.refresh_item().item.get('flagCount', 0) == 1

    # messageprocess, verify flagCount is decremented
    chat_message_postprocessor.message_flag_deleted(message.id)
    assert message.refresh_item().item.get('flagCount', 0) == 0

    # messageprocess again, verify fails softly
    with caplog.at_level(logging.WARNING):
        chat_message_postprocessor.message_flag_deleted(message.id)
    assert len(caplog.records) == 1
    assert 'Failed to decrement flagCount' in caplog.records[0].msg
    assert message.refresh_item().item.get('flagCount', 0) == 0
