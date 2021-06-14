from uuid import uuid4

import pendulum
import pytest


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_user_pool_entry(user_id, username, verified_email=f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user
user3 = user


@pytest.fixture
def chat(chat_manager, user2, user3):
    yield chat_manager.add_direct_chat(str(uuid4()), user2.id, user3.id)


def test_add_chat_message(chat_message_manager):
    chat_id, text = str(uuid4()), str(uuid4())
    before = pendulum.now('utc')
    message = chat_message_manager.add_chat_message(chat_id, text)
    after = pendulum.now('utc')
    assert message.id  # a new uuid4
    assert message.chat_id == chat_id
    assert message.user_id is None
    assert message.text == text
    assert message.text_tags == []
    assert before < message.created_at < after
    assert message.is_initial is False


def test_add_chat_message_with_message_id(chat_message_manager):
    message_id = str(uuid4())
    message = chat_message_manager.add_chat_message(str(uuid4()), str(uuid4()), message_id=message_id)
    assert message.id == message_id


def test_add_chat_message_with_user_id(chat_message_manager):
    user_id = str(uuid4())
    message = chat_message_manager.add_chat_message(str(uuid4()), str(uuid4()), user_id=user_id)
    assert message.user_id == user_id


def test_add_chat_message_with_text_tags(chat_message_manager, user):
    username = user.item['username']
    text = f'whats up with @{username}?'
    message = chat_message_manager.add_chat_message(str(uuid4()), text)
    assert message.text == text
    assert message.text_tags == [{'tag': f'@{username}', 'userId': user.id}]


def test_add_chat_message_with_now(chat_message_manager):
    now = pendulum.now('utc')
    message = chat_message_manager.add_chat_message(str(uuid4()), 'lore', now=now)
    assert message.created_at == now


@pytest.mark.parametrize('is_initial', [False, True])
def test_add_chat_message_with_is_initial(chat_message_manager, chat, is_initial):
    message = chat_message_manager.add_chat_message(str(uuid4()), 'lore ipsum', is_initial=is_initial)
    assert message.is_initial == is_initial


def test_add_system_message_group_created(chat_message_manager, chat, user):
    assert user.username

    # add the message, check it looks ok
    message = chat_message_manager.add_system_message_group_created(chat.id, user.username)
    assert message.item['text'] == f'@{user.username} created the group'
    assert message.item['textTags'] == [{'tag': f'@{user.username}', 'userId': user.id}]
    assert message.is_initial is True

    # add another message, check it looks ok
    message = chat_message_manager.add_system_message_group_created(chat.id, user.username, name='group name')
    assert message.item['text'] == f'@{user.username} created the group "group name"'
    assert message.item['textTags'] == [{'tag': f'@{user.username}', 'userId': user.id}]
    assert message.is_initial is True


def test_add_system_message_added_to_group(chat_message_manager, chat, user):
    assert user.username
    message = chat_message_manager.add_system_message_added_to_group(chat.id, user.username)
    assert message.item['text'] == f'@{user.username} was added to the group'
    assert len(message.item['textTags']) == 1
    assert message.is_initial is False


def test_add_system_message_left_group(chat_message_manager, chat, user):
    assert user.username

    # user leaves
    message = chat_message_manager.add_system_message_left_group(chat.id, user.username)
    assert message.item['text'] == f'@{user.username} left the group'
    assert len(message.item['textTags']) == 1
    assert message.is_initial is False


def test_add_system_message_group_name_edited(chat_message_manager, chat):
    # user changes the name
    message = chat_message_manager.add_system_message_group_name_edited(chat.id, '4eva')
    assert message.item['text'] == 'The name of the group was changed to "4eva"'
    assert len(message.item['textTags']) == 0
    assert message.is_initial is False

    # user deletes the name the name
    message = chat_message_manager.add_system_message_group_name_edited(chat.id, None)
    assert message.item['text'] == 'The name of the group was deleted'
    assert len(message.item['textTags']) == 0
    assert message.is_initial is False
