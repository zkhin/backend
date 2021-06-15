import logging
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.models.chat_message.enums import ChatMessageNotificationType


@pytest.fixture
def user1(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_user_pool_entry(user_id, username, verified_email=f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user1


@pytest.fixture
def chat(chat_manager, user1, user2):
    chat_id = str(uuid4())
    chat = chat_manager.add_direct_chat(chat_id, user1.id, user2.id)
    for member_item in chat_manager.on_chat_add(chat_id, chat.item):
        chat_manager.on_chat_member_add(chat_id, member_item)
    yield chat


@pytest.fixture
def message(chat_message_manager, chat, user1):
    yield chat_message_manager.add_chat_message(chat.id, 'lore ipsum', user_id=user1.id)


@pytest.fixture
def group_chat(chat_manager, user1):
    chat_id = str(uuid4())
    chat = chat_manager.add_group_chat(chat_id, user1.id, [])
    for member_item in chat_manager.on_chat_add(chat_id, chat.item):
        chat_manager.on_chat_member_add(chat_id, member_item)
    yield chat


@pytest.fixture
def group_chat2(chat_manager, user1, user2):
    "user1 and user2 are initial members, user3 is not"
    chat_id = str(uuid4())
    chat = chat_manager.add_group_chat(chat_id, user1.id, [user2.id])
    for member_item in chat_manager.on_chat_add(chat_id, chat.item):
        chat_manager.on_chat_member_add(chat_id, member_item)
    yield chat


def test_on_chat_add_adds_system_message_for_group_chat(chat_message_manager, group_chat):
    assert list(chat_message_manager.dynamo.generate_chat_messages_by_chat(group_chat.id)) == []
    chat_message_manager.on_chat_add(group_chat.id, group_chat.item)
    messages = [
        chat_message_manager.init_chat_message(item)
        for item in chat_message_manager.dynamo.generate_chat_messages_by_chat(group_chat.id)
    ]
    assert len(messages) == 1
    assert messages[0].user_id is None
    assert 'created the group' in messages[0].text
    assert messages[0].is_initial is True


def test_on_chat_add_does_not_add_system_message_for_direct_chat(chat_message_manager, chat):
    assert list(chat_message_manager.dynamo.generate_chat_messages_by_chat(chat.id)) == []
    chat_message_manager.on_chat_add(chat.id, chat.item)
    assert list(chat_message_manager.dynamo.generate_chat_messages_by_chat(chat.id)) == []


def test_on_chat_add_adds_inital_system_message(chat_message_manager, chat):
    text = str(uuid4())
    assert list(chat_message_manager.dynamo.generate_chat_messages_by_chat(chat.id)) == []
    chat_message_manager.on_chat_add(chat.id, {**chat.item, 'initialMessageText': text})
    messages = [
        chat_message_manager.init_chat_message(item)
        for item in chat_message_manager.dynamo.generate_chat_messages_by_chat(chat.id)
    ]
    assert len(messages) == 1
    assert messages[0].user_id is None
    assert messages[0].text == text
    assert messages[0].is_initial is True


def test_on_chat_add_adds_inital_user_message(chat_message_manager, chat, user1):
    mid, text = str(uuid4()), str(uuid4())
    assert list(chat_message_manager.dynamo.generate_chat_messages_by_chat(chat.id)) == []
    chat_message_manager.on_chat_add(chat.id, {**chat.item, 'initialMessageId': mid, 'initialMessageText': text})
    messages = [
        chat_message_manager.init_chat_message(item)
        for item in chat_message_manager.dynamo.generate_chat_messages_by_chat(chat.id)
    ]
    assert len(messages) == 1
    assert messages[0].id == mid
    assert messages[0].user_id == user1.id
    assert messages[0].text == text
    assert messages[0].is_initial is True


def test_on_chat_name_change_asserts_change(chat_message_manager, group_chat):
    with pytest.raises(AssertionError):
        chat_message_manager.on_chat_name_change(group_chat.id, group_chat.item, group_chat.item)
    item = {**group_chat.item, 'name': str(uuid4())}
    with pytest.raises(AssertionError):
        chat_message_manager.on_chat_name_change(group_chat.id, item, item)


def test_on_chat_name_change_adds_system_message(chat_message_manager, group_chat):
    name = str(uuid4())
    assert list(chat_message_manager.dynamo.generate_chat_messages_by_chat(group_chat.id)) == []
    chat_message_manager.on_chat_name_change(group_chat.id, {**group_chat.item, 'name': name}, group_chat.item)
    messages = [
        chat_message_manager.init_chat_message(item)
        for item in chat_message_manager.dynamo.generate_chat_messages_by_chat(group_chat.id)
    ]
    assert len(messages) == 1
    assert messages[0].user_id is None
    assert name in messages[0].text


def test_on_chat_member_add_does_not_throw_when_chat_dne(chat_message_manager, chat, user1):
    member_item = chat.member_dynamo.get(chat.id, user1.id)
    chat.delete()
    assert chat.refresh_item().item is None
    chat_message_manager.on_chat_member_add(chat.id, member_item)


def test_on_chat_member_add_does_not_throw_when_user_dne(chat_message_manager, chat, user1):
    member_item = chat.member_dynamo.get(chat.id, user1.id)
    assert user1.delete().refresh_item().item is None
    chat_message_manager.on_chat_member_add(chat.id, member_item)


def test_on_chat_member_add_does_not_add_message_for_non_group_chat(chat_message_manager, chat, user1):
    member_item = chat.member_dynamo.get(chat.id, user1.id)
    assert list(chat_message_manager.dynamo.generate_chat_messages_by_chat(chat.id)) == []
    chat_message_manager.on_chat_member_add(chat.id, member_item)
    assert list(chat_message_manager.dynamo.generate_chat_messages_by_chat(chat.id)) == []


def test_on_chat_member_add_user_adds_message_when_is_creator(chat_message_manager, group_chat2, user1):
    member_item = group_chat2.member_dynamo.get(group_chat2.id, user1.id)
    assert list(chat_message_manager.dynamo.generate_chat_messages_by_chat(group_chat2.id)) == []
    chat_message_manager.on_chat_member_add(group_chat2.id, member_item)
    messages = [
        chat_message_manager.init_chat_message(item)
        for item in chat_message_manager.dynamo.generate_chat_messages_by_chat(group_chat2.id)
    ]
    assert len(messages) == 1
    assert messages[0].user_id is None
    assert messages[0].created_at == group_chat2.created_at.add(microseconds=1)
    assert user1.username in messages[0].text
    assert 'added to the group' in messages[0].text


def test_on_chat_member_add_user_adds_message_when_is_initial(chat_message_manager, group_chat2, user2):
    member_item = group_chat2.member_dynamo.get(group_chat2.id, user2.id)
    assert list(chat_message_manager.dynamo.generate_chat_messages_by_chat(group_chat2.id)) == []
    chat_message_manager.on_chat_member_add(group_chat2.id, member_item)
    messages = [
        chat_message_manager.init_chat_message(item)
        for item in chat_message_manager.dynamo.generate_chat_messages_by_chat(group_chat2.id)
    ]
    assert len(messages) == 1
    assert messages[0].user_id is None
    assert messages[0].created_at == group_chat2.created_at.add(microseconds=2)
    assert user2.username in messages[0].text
    assert 'added to the group' in messages[0].text


def test_on_chat_member_add_user_adds_message_when_is_not_initial(chat_message_manager, group_chat, user1, user2):
    group_chat.add(user1.id, [user2.id])
    member_item = group_chat.member_dynamo.get(group_chat.id, user2.id)
    assert list(chat_message_manager.dynamo.generate_chat_messages_by_chat(group_chat.id)) == []
    chat_message_manager.on_chat_member_add(group_chat.id, member_item)
    messages = [
        chat_message_manager.init_chat_message(item)
        for item in chat_message_manager.dynamo.generate_chat_messages_by_chat(group_chat.id)
    ]
    assert len(messages) == 1
    assert messages[0].user_id is None
    assert messages[0].created_at > group_chat.created_at
    assert user2.username in messages[0].text
    assert 'added to the group' in messages[0].text


def test_on_chat_member_delete_does_not_throw_when_chat_dne(chat_message_manager, group_chat, user1):
    group_chat.delete()
    assert group_chat.refresh_item().item is None
    member_item = group_chat.member_dynamo.get(group_chat.id, user1.id)
    chat_message_manager.on_chat_member_delete(group_chat.id, member_item)


def test_on_chat_member_delete_does_not_throw_when_user_and_user_deleted_dne(
    chat_message_manager, group_chat, user1
):
    user1.delete()
    assert user1.refresh_item().item is None
    member_item = group_chat.member_dynamo.get(group_chat.id, user1.id)
    chat_message_manager.on_chat_member_delete(group_chat.id, member_item)


def test_on_chat_member_delete_adds_message_for_group_chat(chat_message_manager, group_chat, user1):
    assert list(chat_message_manager.dynamo.generate_chat_messages_by_chat(group_chat.id)) == []
    member_item = group_chat.member_dynamo.get(group_chat.id, user1.id)
    chat_message_manager.on_chat_member_delete(group_chat.id, member_item)
    messages = [
        chat_message_manager.init_chat_message(item)
        for item in chat_message_manager.dynamo.generate_chat_messages_by_chat(group_chat.id)
    ]
    assert len(messages) == 1
    assert messages[0].user_id is None
    assert 'left the group' in messages[0].text
    assert user1.username in messages[0].text


def test_on_chat_member_delete_does_not_add_message_for_non_group_chat(chat_message_manager, chat, user1):
    assert list(chat_message_manager.dynamo.generate_chat_messages_by_chat(chat.id)) == []
    member_item = chat.member_dynamo.get(chat.id, user1.id)
    chat_message_manager.on_chat_member_delete(chat.id, member_item)
    assert list(chat_message_manager.dynamo.generate_chat_messages_by_chat(chat.id)) == []


def test_on_chat_member_delete_adds_message_for_group_chat_username_from_user_deleted(
    chat_message_manager, group_chat, user1
):
    user1.delete()
    user1.dynamo.add_user_deleted(user1.id, user1.username)
    assert list(chat_message_manager.dynamo.generate_chat_messages_by_chat(group_chat.id)) == []
    member_item = group_chat.member_dynamo.get(group_chat.id, user1.id)
    chat_message_manager.on_chat_member_delete(group_chat.id, member_item)
    messages = [
        chat_message_manager.init_chat_message(item)
        for item in chat_message_manager.dynamo.generate_chat_messages_by_chat(group_chat.id)
    ]
    assert len(messages) == 1
    assert messages[0].user_id is None
    assert 'left the group' in messages[0].text
    assert user1.username in messages[0].text


def test_on_chat_message_add_does_not_throw_when_chat_dne(chat_message_manager, message):
    message.chat.delete()
    assert message.chat.refresh_item().item is None
    chat_message_manager.on_chat_message_add(message.id, message.item)


def test_on_chat_message_add_triggers_notifications_when_is_initial(
    chat_message_manager, group_chat2, user1, user2
):
    # remove user2's member item to simulate the chat messsage being processed by the
    # dynamo stream handler before user2's member item is added to the GSI
    group_chat2.member_dynamo.delete(group_chat2.id, user2.id)
    assert group_chat2.member_dynamo.get(group_chat2.id, user2.id) is None
    message = chat_message_manager.add_chat_message(group_chat2.id, 'lore', user_id=user1.id, is_initial=True)
    with patch.object(chat_message_manager.appsync, 'trigger_notification') as tn_mock:
        chat_message_manager.on_chat_message_add(message.id, message.item)
    # check the message is still sent to user2, even though no member item exists in GSI
    assert tn_mock.call_count == 1
    assert tn_mock.call_args.args[0] == ChatMessageNotificationType.ADDED
    assert tn_mock.call_args.args[1] == user2.id


def test_on_chat_message_add_triggers_notifications_when_is_not_initial(
    chat_message_manager, group_chat2, user1, user2
):
    # remove user2's member item to simulate the chat messsage being processed by the
    # dynamo stream handler before user2's member item is added to the GSI
    group_chat2.member_dynamo.delete(group_chat2.id, user2.id)
    assert group_chat2.member_dynamo.get(group_chat2.id, user2.id) is None
    message = chat_message_manager.add_chat_message(group_chat2.id, 'lore', user_id=user1.id)
    with patch.object(chat_message_manager.appsync, 'trigger_notification') as tn_mock:
        chat_message_manager.on_chat_message_add(message.id, message.item)
    # since this wasn't an 'initial' message, we trust the GSI when it says user2 isn't part of the chat
    assert tn_mock.call_count == 0


def test_on_chat_message_text_change_asserts_text_changed(chat_message_manager, message):
    with pytest.raises(AssertionError, match='text did not change'):
        chat_message_manager.on_chat_message_text_change(message.id, message.item, message.item)


def test_on_chat_message_text_change_triggers_notifications(chat_message_manager, message, user2):
    text = str(uuid4())
    with patch.object(chat_message_manager.appsync, 'trigger_notification') as tn_mock:
        chat_message_manager.on_chat_message_text_change(message.id, {**message.item, 'text': text}, message.item)
    assert tn_mock.call_count == 1
    assert tn_mock.call_args.args[0] == ChatMessageNotificationType.EDITED
    assert tn_mock.call_args.args[1] == user2.id


def test_on_chat_message_delete_triggers_notifications(chat_message_manager, message, user2):
    with patch.object(chat_message_manager.appsync, 'trigger_notification') as tn_mock:
        chat_message_manager.on_chat_message_delete(message.id, message.item)
    assert tn_mock.call_count == 1
    assert tn_mock.call_args.args[0] == ChatMessageNotificationType.DELETED
    assert tn_mock.call_args.args[1] == user2.id


def test_on_flag_add(chat_message_manager, message):
    # check & configure starting state
    assert message.refresh_item().item.get('flagCount', 0) == 0
    for _ in range(8):
        message.chat.dynamo.increment_user_count(message.chat_id)
    assert message.chat.refresh_item().item['userCount'] == 10  # just above cutoff for one flag

    # messageprocess, verify flagCount is incremented & not force achived
    chat_message_manager.on_flag_add(message.id, new_item={})
    assert message.refresh_item().item.get('flagCount', 0) == 1


def test_on_flag_add_force_delete_by_crowdsourced_criteria(chat_message_manager, message, caplog):
    # configure and check starting state
    assert message.refresh_item().item.get('flagCount', 0) == 0
    for _ in range(7):
        message.chat.dynamo.increment_user_count(message.chat_id)
    assert message.chat.refresh_item().item['userCount'] == 9  # just below 10% cutoff for one flag

    # postprocess, verify flagCount is incremented and force archived
    chat_message_manager.on_flag_add(message.id, new_item={})
    with caplog.at_level(logging.WARNING):
        chat_message_manager.on_flag_add(message.id, new_item={})
    assert len(caplog.records) == 1
    assert 'Force deleting chat message' in caplog.records[0].msg
    assert message.refresh_item().item is None


def test_on_chat_delete_delete_messages(chat_message_manager, chat):
    # add two messsages
    message_id_1, message_id_2 = str(uuid4()), str(uuid4())
    chat_message_manager.add_chat_message(chat.id, 'lore', message_id=message_id_1)
    chat_message_manager.add_chat_message(chat.id, 'ipsum', message_id=message_id_2)
    assert chat_message_manager.get_chat_message(message_id_1)
    assert chat_message_manager.get_chat_message(message_id_2)

    # trigger, verify messages are gone
    chat_message_manager.on_chat_delete_delete_messages(chat.id, old_item=chat.item)
    assert chat_message_manager.get_chat_message(message_id_1) is None
    assert chat_message_manager.get_chat_message(message_id_2) is None
