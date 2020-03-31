from unittest.mock import Mock, call

import pendulum
import pytest

from app.models.chat.enums import ChatType
from app.models.chat.exceptions import ChatException


@pytest.fixture
def user1(user_manager):
    yield user_manager.create_cognito_only_user('pbuid', 'pbUname')


@pytest.fixture
def user2(user_manager):
    yield user_manager.create_cognito_only_user('pbuid2', 'pbUname2')


@pytest.fixture
def user3(user_manager):
    yield user_manager.create_cognito_only_user('pbuid3', 'pbUname3')


def test_cant_add_direct_chat_blocked(chat_manager, block_manager, user1, user2):
    # user1 blocks user2
    assert block_manager.block(user1, user2)
    chat_id = 'cid'

    with pytest.raises(ChatException, match='has blocked'):
        chat_manager.add_direct_chat(chat_id, user1.id, user2.id)

    with pytest.raises(ChatException, match='has blocked'):
        chat_manager.add_direct_chat(chat_id, user2.id, user1.id)


def test_cant_add_direct_chat_with_self(chat_manager, user1):
    chat_id = 'cid'
    with pytest.raises(ChatException, match='with themselves'):
        chat_manager.add_direct_chat(chat_id, user1.id, user1.id)


def test_cant_add_direct_chat_users_dont_exist(chat_manager, user1, user2):
    with pytest.raises(ChatException, match='Unable to increment'):
        chat_manager.add_direct_chat('cid1', 'uid-dne', user2.id)

    # verify no error
    chat_manager.add_direct_chat('cid3', user1.id, user2.id)


def test_cant_add_direct_chat_already_exists(chat_manager, user1, user2):
    # add the chat
    chat_manager.add_direct_chat('cid3', user1.id, user2.id)

    # verify can't add it again, even with new chat id
    with pytest.raises(ChatException, match='already exists'):
        chat_manager.add_direct_chat('cid4', user1.id, user2.id)
    with pytest.raises(ChatException, match='already exists'):
        chat_manager.add_direct_chat('cid4', user2.id, user1.id)


def test_add_direct_chat(chat_manager, user1, user2):
    now = pendulum.now('utc')

    # verify user's chat counts start at zero
    assert user1.item.get('chatCount', 0) == 0
    assert user2.item.get('chatCount', 0) == 0

    # add the chat, verify it looks ok
    chat_id = 'cid'
    chat = chat_manager.add_direct_chat(chat_id, user1.id, user2.id, now=now)
    assert chat.id == chat_id
    assert chat.type == ChatType.DIRECT
    assert chat.item['createdAt'] == now.to_iso8601_string()
    assert chat.item['createdByUserId'] == user1.id
    assert chat.item.get('messageCount', 0) == 0
    assert chat.item.get('name') is None

    # verify user's chat counts have incremented
    user1.refresh_item()
    assert user1.item.get('chatCount', 0) == 1
    user2.refresh_item()
    assert user2.item.get('chatCount', 0) == 1

    # verify chat memberships for both users were created
    user_ids = chat_manager.dynamo.generate_chat_membership_user_ids_by_chat(chat_id)
    assert sorted(user_ids) == sorted([user1.id, user2.id])


def test_add_minimal_group_chat(chat_manager, user1):
    # verify and set up starting state
    assert user1.item.get('chatCount', 0) == 0
    chat_manager.chat_message_manager = Mock()

    # add the chat, verify it looks ok
    chat_id = 'cid'
    before = pendulum.now('utc')
    chat = chat_manager.add_group_chat(chat_id, user1.id)
    after = pendulum.now('utc')
    assert chat.id == chat_id
    assert chat.type == ChatType.GROUP
    assert chat.item.get('messageCount', 0) == 0
    assert chat.item.get('name') is None
    assert chat.item['createdByUserId'] == user1.id
    created_at = pendulum.parse(chat.item['createdAt'])
    assert before <= created_at
    assert after >= created_at

    # verify user's chat counts have incremented
    user1.refresh_item()
    assert user1.item.get('chatCount', 0) == 1

    # verify chat membership was created
    user_ids = list(chat_manager.dynamo.generate_chat_membership_user_ids_by_chat(chat_id))
    assert user_ids == [user1.id]

    # verify the system chat message was triggered
    assert chat_manager.chat_message_manager.mock_calls == [
        call.add_system_message_group_created(chat_id, user1.id, name=None, now=created_at),
    ]


def test_add_maximal_group_chat(chat_manager, user1):
    # verify and set up starting state
    assert user1.item.get('chatCount', 0) == 0
    chat_manager.chat_message_manager = Mock()

    # add the chat, verify it looks ok
    chat_id = 'cid'
    name = 'lore'
    now = pendulum.now('utc')
    chat = chat_manager.add_group_chat(chat_id, user1.id, name=name, now=now)
    assert chat.id == chat_id
    assert chat.type == ChatType.GROUP
    assert chat.item.get('messageCount', 0) == 0
    assert chat.item['name'] == name
    assert chat.item['createdByUserId'] == user1.id
    assert pendulum.parse(chat.item['createdAt']) == now

    # verify user's chat counts have incremented
    user1.refresh_item()
    assert user1.item.get('chatCount', 0) == 1

    # verify chat membership was created
    user_ids = list(chat_manager.dynamo.generate_chat_membership_user_ids_by_chat(chat_id))
    assert user_ids == [user1.id]

    # verify the system chat message was triggered
    assert chat_manager.chat_message_manager.mock_calls == [
        call.add_system_message_group_created(chat_id, user1.id, name=name, now=now),
    ]


def test_leave_all_chats(chat_manager, user1, user2, user3):
    # user1 opens up direct chats with both of the other two users
    chat_id_1 = 'cid1'
    chat_id_2 = 'cid2'
    chat_manager.add_direct_chat(chat_id_1, user1.id, user2.id)
    chat_manager.add_direct_chat(chat_id_2, user1.id, user3.id)

    # user1 sets up a group chat with only themselves in it, and another with user2
    chat_id_3 = 'cid3'
    chat_id_4 = 'cid4'
    chat_manager.add_group_chat(chat_id_3, user1.id)
    chat_manager.add_group_chat(chat_id_4, user1.id).add(user1.id, [user2.id])

    # verify that's reflected in the user totals
    user1.refresh_item()
    user2.refresh_item()
    user3.refresh_item()
    assert user1.item['chatCount'] == 4
    assert user2.item['chatCount'] == 2
    assert user3.item['chatCount'] == 1

    # verify we see the chat and chat_memberships in the DB
    assert chat_manager.dynamo.get_chat(chat_id_1)['userCount'] == 2
    assert chat_manager.dynamo.get_chat(chat_id_2)['userCount'] == 2
    assert chat_manager.dynamo.get_chat(chat_id_3)['userCount'] == 1
    assert chat_manager.dynamo.get_chat(chat_id_4)['userCount'] == 2
    assert chat_manager.dynamo.get_chat_membership(chat_id_1, user1.id)
    assert chat_manager.dynamo.get_chat_membership(chat_id_1, user2.id)
    assert chat_manager.dynamo.get_chat_membership(chat_id_2, user1.id)
    assert chat_manager.dynamo.get_chat_membership(chat_id_2, user3.id)
    assert chat_manager.dynamo.get_chat_membership(chat_id_3, user1.id)
    assert chat_manager.dynamo.get_chat_membership(chat_id_4, user1.id)
    assert chat_manager.dynamo.get_chat_membership(chat_id_4, user2.id)

    # user1 leaves all their chats, which should trigger deletes of both direct chats
    chat_manager.leave_all_chats(user1.id)

    # verify that's reflected in the user totals
    user1.refresh_item()
    user2.refresh_item()
    user3.refresh_item()
    assert user1.item['chatCount'] == 0
    assert user2.item['chatCount'] == 1
    assert user3.item['chatCount'] == 0

    # verify we see the chat and chat_memberships in the DB
    assert chat_manager.dynamo.get_chat(chat_id_1) is None
    assert chat_manager.dynamo.get_chat(chat_id_2) is None
    assert chat_manager.dynamo.get_chat(chat_id_3) is None
    assert chat_manager.dynamo.get_chat(chat_id_4)['userCount'] == 1
    assert chat_manager.dynamo.get_chat_membership(chat_id_1, user1.id) is None
    assert chat_manager.dynamo.get_chat_membership(chat_id_1, user2.id) is None
    assert chat_manager.dynamo.get_chat_membership(chat_id_2, user1.id) is None
    assert chat_manager.dynamo.get_chat_membership(chat_id_2, user3.id) is None
    assert chat_manager.dynamo.get_chat_membership(chat_id_3, user1.id) is None
    assert chat_manager.dynamo.get_chat_membership(chat_id_4, user1.id) is None
    assert chat_manager.dynamo.get_chat_membership(chat_id_4, user2.id)
