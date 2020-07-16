from unittest.mock import Mock, call
from uuid import uuid4

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
