import logging
from unittest.mock import patch
from uuid import uuid4

import pendulum
import pytest

from app.models.chat.exceptions import ChatException


@pytest.fixture
def user1(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_user_pool_entry(user_id, username, verified_email=f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user1
user3 = user1


@pytest.fixture
def direct_chat(chat_manager, user1, user2):
    chat_id = str(uuid4())
    chat = chat_manager.add_direct_chat(chat_id, user1.id, user2.id)
    for member_item in chat_manager.on_chat_add(chat_id, chat.item):
        chat_manager.on_chat_member_add(chat_id, member_item)
    yield chat.refresh_item()


@pytest.fixture
def group_chat(chat_manager, user1):
    chat_id = str(uuid4())
    chat = chat_manager.add_group_chat(chat_id, user1.id, [])
    for member_item in chat_manager.on_chat_add(chat_id, chat.item):
        chat_manager.on_chat_member_add(chat_id, member_item)
    yield chat.refresh_item()


def test_is_member(direct_chat, user1, user2, user3):
    assert direct_chat.is_member(user1.id) is True
    assert direct_chat.is_member(user2.id) is True
    assert direct_chat.is_member(user3.id) is False


def test_is_member_group_chat(group_chat, user1, user2):
    assert group_chat.is_member(user1.id) is True
    assert group_chat.is_member(user2.id) is False


def test_cant_edit_non_group_chat(direct_chat):
    with pytest.raises(ChatException, match='non-GROUP chat'):
        direct_chat.edit(name='new name')


def test_edit_group_chat(group_chat, user1):
    # verify starting state
    assert 'name' not in group_chat.item

    # set a name
    group_chat.edit(name='name 1')
    assert group_chat.item['name'] == 'name 1'
    assert group_chat.item == group_chat.refresh_item().item

    # change the name
    group_chat.edit(name='name 2')
    assert group_chat.item['name'] == 'name 2'
    assert group_chat.item == group_chat.refresh_item().item

    # delete the name
    group_chat.edit(name='')
    assert 'name' not in group_chat.item
    assert group_chat.item == group_chat.refresh_item().item


def test_add_one_user_success(group_chat, user1, user2):
    assert group_chat.member_dynamo.get(group_chat.id, user2.id) is None
    before = pendulum.now('utc')
    group_chat.add(user1.id, [user2.id])
    after = pendulum.now('utc')
    member_item = group_chat.member_dynamo.get(group_chat.id, user2.id)
    assert member_item
    assert before <= pendulum.parse(member_item['createdAt']) <= after


def test_add_two_users_success_with_options(group_chat, user1, user2, user3):
    assert group_chat.member_dynamo.get(group_chat.id, user2.id) is None
    assert group_chat.member_dynamo.get(group_chat.id, user3.id) is None
    now = pendulum.now('utc')
    group_chat.add(user1.id, [user2.id, user3.id], now=now)
    member_item1 = group_chat.member_dynamo.get(group_chat.id, user2.id)
    member_item2 = group_chat.member_dynamo.get(group_chat.id, user3.id)
    assert member_item1
    assert member_item2
    assert pendulum.parse(member_item1['createdAt']) == now
    assert pendulum.parse(member_item2['createdAt']) == now


def test_add_cant_add_to_non_group_chat(direct_chat):
    with pytest.raises(ChatException, match='non-GROUP chat'):
        direct_chat.add('uid', ['new-uid'])


def test_add_cant_add_user_that_fails_chat_validation(group_chat, user1, user2, caplog):
    assert group_chat.member_dynamo.get(group_chat.id, user2.id) is None
    msg = str(uuid4())
    with patch.object(group_chat.chat_manager, 'validate_can_chat', side_effect=ChatException(msg)):
        with caplog.at_level(logging.WARNING):
            group_chat.add(user1.id, [user2.id])
    assert group_chat.member_dynamo.get(group_chat.id, user2.id) is None
    assert len(caplog.records) == 1
    assert msg in caplog.records[0].msg


def test_add_cant_add_user_already_in_chat(group_chat, user1, user2, caplog):
    group_chat.add(user1.id, [user2.id])
    assert group_chat.member_dynamo.get(group_chat.id, user2.id)
    with caplog.at_level(logging.WARNING):
        group_chat.add(user1.id, [user2.id])
    assert len(caplog.records) == 1
    assert 'is already in chat' in caplog.records[0].msg


def test_add_two_users_one_fails_validation_one_succeeds(group_chat, user1, user2, user3, caplog):
    msg = str(uuid4())

    def validate(user_id_1, user_id_2):
        if user_id_2 == user2.id:
            raise ChatException(msg)

    assert group_chat.member_dynamo.get(group_chat.id, user2.id) is None
    assert group_chat.member_dynamo.get(group_chat.id, user3.id) is None
    with patch.object(group_chat.chat_manager, 'validate_can_chat', new=validate):
        with caplog.at_level(logging.WARNING):
            group_chat.add(user1.id, [user2.id, user3.id])
    assert len(caplog.records) == 1
    assert msg in caplog.records[0].msg
    assert user2.id in caplog.records[0].msg
    assert group_chat.member_dynamo.get(group_chat.id, user2.id) is None
    assert group_chat.member_dynamo.get(group_chat.id, user3.id)


def test_add_two_users_one_fails_already_in_chat_one_succeeds(group_chat, user1, user2, user3, caplog):
    group_chat.add(user1.id, [user3.id])
    assert group_chat.member_dynamo.get(group_chat.id, user2.id) is None
    assert group_chat.member_dynamo.get(group_chat.id, user3.id)
    with caplog.at_level(logging.WARNING):
        group_chat.add(user1.id, [user2.id, user3.id])
    assert len(caplog.records) == 1
    assert 'is already in chat' in caplog.records[0].msg
    assert user3.id in caplog.records[0].msg
    assert group_chat.member_dynamo.get(group_chat.id, user2.id)
    assert group_chat.member_dynamo.get(group_chat.id, user3.id)


def test_leave_success(group_chat, user1, user2):
    group_chat.add(user1.id, [user2.id])
    assert group_chat.member_dynamo.get(group_chat.id, user2.id)
    group_chat.leave(user2.id)
    assert group_chat.member_dynamo.get(group_chat.id, user2.id) is None


def test_leave_cant_leave_group_chat_were_not_in(group_chat, user2):
    with pytest.raises(ChatException, match='is not a member of chat'):
        group_chat.leave(user2)


def test_leave_cant_leave_non_group_chat(direct_chat):
    with pytest.raises(ChatException, match='non-GROUP chat'):
        direct_chat.leave(['new-uid'])


def test_delete(group_chat, direct_chat):
    # test deleting the group chat
    assert group_chat.refresh_item().item
    group_chat.delete()
    assert group_chat.refresh_item().item is None

    # test deleting the direct chat
    assert direct_chat.refresh_item().item
    direct_chat.delete()
    assert direct_chat.refresh_item().item is None


def test_cant_flag_chat_we_are_not_in(direct_chat, user1, user2, user3):
    # user3 is not part of the chat, check they can't flag it
    with pytest.raises(ChatException, match='User is not part of chat'):
        direct_chat.flag(user3)

    # verify user2, who is part of the chat, can flag without exception
    assert direct_chat.flag(user2)


def test_is_crowdsourced_forced_removal_criteria_met_direct_chat(direct_chat):
    # check starting state
    assert direct_chat.item.get('flagCount', 0) == 0
    assert direct_chat.is_crowdsourced_forced_removal_criteria_met() is False

    # simulate a flag in a direct chat
    direct_chat.item['flagCount'] = 2
    assert direct_chat.is_crowdsourced_forced_removal_criteria_met() is True


def test_is_crowdsourced_forced_removal_criteria_met_group_chat(group_chat):
    # check starting state
    assert group_chat.item.get('flagCount', 0) == 0
    assert group_chat.is_crowdsourced_forced_removal_criteria_met() is False

    group_chat.item['flagCount'] = 1
    assert group_chat.is_crowdsourced_forced_removal_criteria_met() is False

    group_chat.item['flagCount'] = 2
    assert group_chat.is_crowdsourced_forced_removal_criteria_met() is True
