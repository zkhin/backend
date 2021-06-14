import logging
from unittest.mock import patch
from uuid import uuid4

import pendulum
import pytest

from app.mixins.view.enums import ViewedStatus
from app.models.chat.enums import ChatType
from app.models.chat.exceptions import ChatException
from app.models.user.enums import UserStatus


@pytest.fixture
def user1(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_user_pool_entry(user_id, username, verified_email=f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user1
user3 = user1


def test_add_direct_chat_failure_intial_message_id_and_text_consistentcy(chat_manager):
    with pytest.raises(AssertionError):
        chat_manager.add_direct_chat(str(uuid4()), str(uuid4()), str(uuid4()), initial_message_id='not-none')


def test_add_direct_chat_failure_validate_can_chat_fails(chat_manager, user1, user2):
    msg = str(uuid4())
    with patch.object(chat_manager, 'validate_can_chat', side_effect=ChatException(msg)):
        with pytest.raises(ChatException, match=msg):
            chat_manager.add_direct_chat('cid3', user1.id, user2.id)


def test_add_direct_chat_failure_already_exists(chat_manager, user1, user2):
    # add the chat
    chat_manager.add_direct_chat('cid3', user1.id, user2.id)

    # verify can't add it again, even with new chat id
    with patch.object(chat_manager, 'validate_can_chat'):
        with pytest.raises(ChatException, match='already exists'):
            chat_manager.add_direct_chat('cid4', user1.id, user2.id)
        with pytest.raises(ChatException, match='already exists'):
            chat_manager.add_direct_chat('cid4', user2.id, user1.id)


def test_add_direct_chat_success_minimal(chat_manager, user1, user2):
    chat_id = str(uuid4())
    before = pendulum.now('utc')
    chat = chat_manager.add_direct_chat(chat_id, user1.id, user2.id)
    after = pendulum.now('utc')
    assert chat.id == chat_id
    assert chat.type == ChatType.DIRECT
    assert before <= chat.created_at <= after
    assert chat.created_by.id == user1.id
    assert chat.created_by_user_id == user1.id
    assert chat.name is None
    assert chat.messages_count == 0
    assert chat.user_count == 0
    assert chat.initial_member_user_ids == sorted([user1.id, user2.id])
    assert chat.initial_message_id is None
    assert chat.initial_message_text is None


def test_add_direct_chat_success_with_options(chat_manager, user1, user2):
    chat_id, msg_id, msg_txt = str(uuid4()), str(uuid4()), str(uuid4())
    now = pendulum.now('utc')
    chat = chat_manager.add_direct_chat(
        chat_id, user1.id, user2.id, initial_message_id=msg_id, initial_message_text=msg_txt, now=now
    )
    assert chat.id == chat_id
    assert chat.type == ChatType.DIRECT
    assert chat.created_at == now
    assert chat.initial_message_id == msg_id
    assert chat.initial_message_text == msg_txt


def test_add_group_chat_failure_intial_message_id_and_text_consistentcy(chat_manager):
    with pytest.raises(AssertionError):
        chat_manager.add_group_chat(str(uuid4()), str(uuid4()), [], initial_message_id='not-none')


def test_add_group_chat_success_minimal(chat_manager, user1):
    chat_id = str(uuid4())
    before = pendulum.now('utc')
    chat = chat_manager.add_group_chat(chat_id, user1.id, [])
    after = pendulum.now('utc')
    assert chat.id == chat_id
    assert chat.type == ChatType.GROUP
    assert before <= chat.created_at <= after
    assert chat.created_by.id == user1.id
    assert chat.created_by_user_id == user1.id
    assert chat.name is None
    assert chat.messages_count == 0
    assert chat.user_count == 0
    assert chat.initial_member_user_ids == sorted([user1.id])
    assert chat.initial_message_id is None
    assert chat.initial_message_text is None


def test_add_group_chat_success_with_options(chat_manager, user1, user2, user3):
    chat_id, msg_id, msg_txt, name = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
    now = pendulum.now('utc')
    chat = chat_manager.add_group_chat(
        chat_id,
        user1.id,
        [user2.id, user3.id],
        initial_message_id=msg_id,
        initial_message_text=msg_txt,
        name=name,
        now=now,
    )
    assert chat.id == chat_id
    assert chat.type == ChatType.GROUP
    assert chat.created_at == now
    assert chat.initial_message_id == msg_id
    assert chat.initial_message_text == msg_txt
    assert chat.name == name
    assert chat.initial_member_user_ids == sorted([user1.id, user2.id, user3.id])


def test_add_group_chat_partial_success_some_users_filtered_out(chat_manager, user1):
    chat_id, user_id_2, user_id_3 = str(uuid4()), str(uuid4()), str(uuid4())

    def validate(uid1, uid2):
        if uid2 == user_id_2:
            raise ChatException()

    with patch.object(chat_manager, 'validate_can_chat', new=validate):
        chat = chat_manager.add_group_chat(chat_id, user1.id, [user_id_2, user_id_3])
    assert chat.id == chat_id
    assert chat.initial_member_user_ids == sorted([user1.id, user_id_3])


def test_record_views(chat_manager, user1, user2, user3, caplog):
    chat_id = str(uuid4())

    # verify can't record views on chat that DNE
    with caplog.at_level(logging.WARNING):
        chat_manager.record_views([chat_id], user1.id)
    assert len(caplog.records) == 1
    assert 'Cannot record view' in caplog.records[0].msg
    assert 'on DNE chat' in caplog.records[0].msg
    assert chat_id in caplog.records[0].msg
    assert user1.id in caplog.records[0].msg

    chat = chat_manager.add_direct_chat(chat_id, user1.id, user2.id)
    chat_manager.on_chat_add(chat_id, chat.item)
    assert chat.get_viewed_status(user1.id) == ViewedStatus.NOT_VIEWED
    assert chat.get_viewed_status(user2.id) == ViewedStatus.NOT_VIEWED
    assert chat.get_viewed_status(user3.id) == ViewedStatus.NOT_VIEWED

    # verify non-member can't record views on chat
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        chat_manager.record_views([chat_id], user3.id)
    assert len(caplog.records) == 1
    assert 'Cannot record view' in caplog.records[0].msg
    assert 'by non-member user' in caplog.records[0].msg
    assert chat_id in caplog.records[0].msg
    assert user3.id in caplog.records[0].msg
    assert chat.get_viewed_status(user3.id) == ViewedStatus.NOT_VIEWED

    # verify member can record views on chat
    caplog.clear()
    chat_manager.record_views([chat_id], user1.id)
    assert caplog.records == []
    assert chat.get_viewed_status(user1.id) == ViewedStatus.VIEWED


def test_validate_can_chat_success(chat_manager, user1, user2):
    chat_manager.validate_can_chat(user1.id, user2.id)  # does not throw


def test_validate_can_chat_failure_themselves(chat_manager, user1):
    with pytest.raises(ChatException, match='themselves'):
        chat_manager.validate_can_chat(user1.id, user1.id)


def test_validate_can_chat_failure_does_not_exist(chat_manager, user1):
    with pytest.raises(ChatException, match='does not exist'):
        chat_manager.validate_can_chat(user1.id, str(uuid4()))


def test_validate_can_chat_failure_blocked(chat_manager, block_manager, user1, user2):
    assert block_manager.block(user1, user2)
    with pytest.raises(ChatException, match='has blocked'):
        chat_manager.validate_can_chat(user1.id, user2.id)
    with pytest.raises(ChatException, match='has been blocked'):
        chat_manager.validate_can_chat(user2.id, user1.id)


def test_validate_can_chat_failure_not_active(chat_manager, user1, user2):
    user2.dynamo.set_user_status(user2.id, UserStatus.ANONYMOUS)
    assert user2.refresh_item().status != UserStatus.ACTIVE
    with pytest.raises(ChatException, match='has non-active status'):
        chat_manager.validate_can_chat(user1.id, user2.id)


def test_validate_can_chat_failure_dating(chat_manager, user1, user2):
    with patch.object(chat_manager.real_dating_client, 'can_contact', return_value=False):
        with pytest.raises(ChatException, match='due to dating'):
            chat_manager.validate_can_chat(user1.id, user2.id)
