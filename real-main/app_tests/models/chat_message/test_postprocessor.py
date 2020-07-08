from unittest.mock import Mock, call, patch
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


def test_run_chat_message_added_or_edited(chat_message_postprocessor, message):
    pk, sk = message.item['partitionKey'], message.item['sortKey']
    old_item = {'key': 'value'}

    # postprocess the user message, verify calls correct
    chat_message_postprocessor.manager = Mock(chat_message_postprocessor.manager)
    chat_message_postprocessor.run(pk, sk, old_item, message.item)
    assert chat_message_postprocessor.manager.mock_calls == [
        call.init_chat_message(message.item),
        call.init_chat_message().on_add_or_edit(old_item),
    ]


def test_run_chat_message_deleted(chat_message_postprocessor, message):
    pk, sk = message.item['partitionKey'], message.item['sortKey']

    # postprocess the user message, verify calls correct
    chat_message_postprocessor.manager = Mock(chat_message_postprocessor.manager)
    chat_message_postprocessor.run(pk, sk, message.item, {})
    assert chat_message_postprocessor.manager.mock_calls == [
        call.init_chat_message(message.item),
        call.init_chat_message().on_delete(),
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

    # postprocess adding that message flag, verify calls correct
    with patch.object(chat_message_postprocessor, 'manager') as manager_mock:
        chat_message_postprocessor.run(pk, sk, {}, flag_item)
    assert manager_mock.on_flag_added.mock_calls == [call(message.id, user2.id)]
    assert manager_mock.on_flag_deleted.mock_calls == []

    # postprocess editing that message flag, verify calls correct
    with patch.object(chat_message_postprocessor, 'manager') as manager_mock:
        chat_message_postprocessor.run(pk, sk, flag_item, flag_item)
    assert manager_mock.on_flag_added.mock_calls == []
    assert manager_mock.on_flag_deleted.mock_calls == []

    # postprocess deleting that message flag, verify calls correct
    with patch.object(chat_message_postprocessor, 'manager') as manager_mock:
        chat_message_postprocessor.run(pk, sk, flag_item, {})
    assert manager_mock.on_flag_added.mock_calls == []
    assert manager_mock.on_flag_deleted.mock_calls == [call(message.id)]
