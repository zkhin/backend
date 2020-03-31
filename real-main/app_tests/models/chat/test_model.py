from unittest.mock import Mock, call

import pendulum
import pytest

from app.models.chat.exceptions import ChatException


@pytest.fixture
def user1(user_manager):
    yield user_manager.create_cognito_only_user('pbuid', 'pbUname')


@pytest.fixture
def user2(user_manager):
    yield user_manager.create_cognito_only_user('pbuid2', 'pbUname2')


@pytest.fixture
def direct_chat(chat_manager, user1, user2):
    yield chat_manager.add_direct_chat('cid', user1.id, user2.id)


@pytest.fixture
def user3(user_manager):
    yield user_manager.create_cognito_only_user('pbuid3', 'pbUname3')


@pytest.fixture
def user4(user_manager):
    yield user_manager.create_cognito_only_user('pbuid4', 'pbUname4')


@pytest.fixture
def group_chat(chat_manager, user1):
    yield chat_manager.add_group_chat('cid2', user1.id)


def test_is_member(direct_chat, user1, user2, user3):
    assert direct_chat.is_member(user1.id) is True
    assert direct_chat.is_member(user2.id) is True
    assert direct_chat.is_member(user3.id) is False


def test_is_member_group_chat(group_chat, user1, user2):
    assert group_chat.is_member(user1.id) is True
    assert group_chat.is_member(user2.id) is False


def test_update_memberships_last_message_activity_at(direct_chat, user1, user2):
    # verify starting state
    membership_1 = direct_chat.dynamo.get_chat_membership(direct_chat.id, user1.id)
    membership_2 = direct_chat.dynamo.get_chat_membership(direct_chat.id, user2.id)
    new_at = pendulum.now('utc')
    assert pendulum.parse(membership_1['gsiK2SortKey'][len('chat/'):]) != new_at
    assert pendulum.parse(membership_2['gsiK2SortKey'][len('chat/'):]) != new_at

    direct_chat.update_memberships_last_message_activity_at(new_at)

    # verify final state
    membership_1 = direct_chat.dynamo.get_chat_membership(direct_chat.id, user1.id)
    membership_2 = direct_chat.dynamo.get_chat_membership(direct_chat.id, user2.id)
    assert pendulum.parse(membership_1['gsiK2SortKey'][len('chat/'):]) == new_at
    assert pendulum.parse(membership_2['gsiK2SortKey'][len('chat/'):]) == new_at


def test_cant_edit_non_group_chat(direct_chat, user1):
    with pytest.raises(ChatException, match='non-GROUP chat'):
        direct_chat.edit(user1.id, name='new name')


def test_edit_group_chat(group_chat, user1):
    # verify starting state
    assert 'name' not in group_chat.item
    group_chat.chat_message_manager = Mock()

    # set a name
    group_chat.edit(user1.id, name='name 1')
    assert group_chat.item['name'] == 'name 1'
    group_chat.refresh_item()
    assert group_chat.item['name'] == 'name 1'
    assert group_chat.chat_message_manager.mock_calls == [
        call.add_system_message_group_name_edited(group_chat.id, user1.id, 'name 1')
    ]
    group_chat.chat_message_manager.reset_mock()

    # change the name
    group_chat.edit(user1.id, name='name 2')
    assert group_chat.item['name'] == 'name 2'
    group_chat.refresh_item()
    assert group_chat.item['name'] == 'name 2'
    assert group_chat.chat_message_manager.mock_calls == [
        call.add_system_message_group_name_edited(group_chat.id, user1.id, 'name 2')
    ]
    group_chat.chat_message_manager.reset_mock()

    # delete the name
    group_chat.edit(user1.id, name='')
    assert 'name' not in group_chat.item
    group_chat.refresh_item()
    assert 'name' not in group_chat.item
    assert group_chat.chat_message_manager.mock_calls == [
        call.add_system_message_group_name_edited(group_chat.id, user1.id, '')
    ]


def test_add(group_chat, user1, user2, user3, user4, user_manager, block_manager):
    group_chat.chat_message_manager = Mock()
    now = pendulum.now('utc')

    # check starting members
    assert group_chat.item['userCount'] == 1
    member_user_ids = list(group_chat.dynamo.generate_chat_membership_user_ids_by_chat(group_chat.id))
    assert member_user_ids == [user1.id]

    # add user2 to the chat
    group_chat.chat_message_manager.reset_mock()
    group_chat.add(user1.id, [user2.id], now=now)
    assert group_chat.item['userCount'] == 2
    group_chat.refresh_item()
    assert group_chat.item['userCount'] == 2
    member_user_ids = list(group_chat.dynamo.generate_chat_membership_user_ids_by_chat(group_chat.id))
    assert sorted(member_user_ids) == sorted([user1.id, user2.id])
    msg_mock = group_chat.chat_message_manager.add_system_message_added_to_group
    assert len(msg_mock.mock_calls) == 1
    assert len(msg_mock.call_args.args) == 3
    assert msg_mock.call_args.args[0] == group_chat.id
    assert msg_mock.call_args.args[1] == user1.id
    assert len(msg_mock.call_args.args[2]) == 1
    assert msg_mock.call_args.args[2][0].id == user2.id  # Note: comparing user instances doesn't work
    assert msg_mock.call_args.kwargs == {'now': now}

    # create two users, one that blocks user2 and one that user2 blocks
    user_blocker = user_manager.create_cognito_only_user('pbuid-blocker', 'pbUname_blocker')
    user_blocked = user_manager.create_cognito_only_user('pbuid-blocked', 'pbUname_blocked')
    block_manager.block(user_blocker, user2)
    block_manager.block(user2, user_blocked)

    # user2 adds user3 and user4, and a bunch of fluff that should get filtered out
    group_chat.chat_message_manager.reset_mock()
    user_ids = [user3.id, user4.id, user1.id, user2.id, user4.id, user_blocker.id, user_blocked.id, 'uid-dne']
    group_chat.add(user2.id, user_ids, now=now)
    assert group_chat.item['userCount'] == 4
    group_chat.refresh_item()
    assert group_chat.item['userCount'] == 4
    member_user_ids = list(group_chat.dynamo.generate_chat_membership_user_ids_by_chat(group_chat.id))
    assert sorted(member_user_ids) == sorted([user1.id, user2.id, user3.id, user4.id])
    msg_mock = group_chat.chat_message_manager.add_system_message_added_to_group
    assert len(msg_mock.mock_calls) == 1
    assert len(msg_mock.call_args.args) == 3
    assert msg_mock.call_args.args[0] == group_chat.id
    assert msg_mock.call_args.args[1] == user2.id
    assert len(msg_mock.call_args.args[2]) == 2
    # Note: comparing user instances doesn't work
    assert sorted(u.id for u in msg_mock.call_args.args[2]) == sorted([user3.id, user4.id])
    assert msg_mock.call_args.kwargs == {'now': now}


def test_cant_add_to_non_group_chat(direct_chat):
    with pytest.raises(ChatException, match='non-GROUP chat'):
        direct_chat.add('uid', ['new-uid'])


def test_leave(group_chat, user1, user2):
    group_chat.chat_message_manager = Mock()

    # check starting members
    assert group_chat.item['userCount'] == 1
    member_user_ids = list(group_chat.dynamo.generate_chat_membership_user_ids_by_chat(group_chat.id))
    assert member_user_ids == [user1.id]

    # user1 adds user2 to the chat
    group_chat.add(user1.id, [user2.id])
    assert group_chat.item['userCount'] == 2
    member_user_ids = list(group_chat.dynamo.generate_chat_membership_user_ids_by_chat(group_chat.id))
    assert sorted(member_user_ids) == sorted([user1.id, user2.id])

    # user1 leaves the chat
    group_chat.chat_message_manager.reset_mock()
    group_chat.leave(user1.id)
    assert group_chat.item['userCount'] == 1
    member_user_ids = list(group_chat.dynamo.generate_chat_membership_user_ids_by_chat(group_chat.id))
    assert member_user_ids == [user2.id]
    assert group_chat.chat_message_manager.mock_calls == [
        call.add_system_message_left_group(group_chat.id, user1.id)
    ]

    # user2 leaves the chat, should trigger the deletion of the chat, and hence no need for new system message
    group_chat.chat_message_manager.reset_mock()
    group_chat.leave(user2.id)
    assert group_chat.item['userCount'] == 0
    group_chat.refresh_item()
    assert group_chat.item is None
    member_user_ids = list(group_chat.dynamo.generate_chat_membership_user_ids_by_chat(group_chat.id))
    assert member_user_ids == []
    assert group_chat.chat_message_manager.mock_calls == [
        call.truncate_chat_messages(group_chat.id),
    ]


def test_cant_leave_group_chat_were_not_in(group_chat, user2):
    with pytest.raises(ChatException, match='delete chat membership'):
        group_chat.leave(user2.id)


def test_cant_leave_non_group_chat(direct_chat):
    with pytest.raises(ChatException, match='non-GROUP chat'):
        direct_chat.leave(['new-uid'])


def test_delete_group_chat(group_chat, user1, chat_message_manager):
    # user1 adds message to the chat
    group_chat.refresh_item()
    assert group_chat.item['messageCount'] == 1
    message_id = 'mid'
    chat_message_manager.add_chat_message(message_id, 'lore ipsum', group_chat.id, user1.id)

    # user1 leaves the chat, but avoid the auto-deletion by faking another user in it
    group_chat.item['userCount'] += 1
    group_chat.leave(user1.id)
    assert group_chat.item['userCount'] == 1
    group_chat.item['userCount'] -= 1

    # verify starting state
    assert list(group_chat.dynamo.generate_chat_membership_user_ids_by_chat(group_chat.id)) == []
    message_items = list(chat_message_manager.dynamo.generate_chat_messages_by_chat(group_chat.id))
    assert len(message_items) == 3
    assert message_items[1]['messageId'] == message_id

    # delete the chat
    group_chat.delete_group_chat()

    # verify starting state
    assert group_chat.dynamo.get_chat(group_chat.id) is None
    assert list(group_chat.dynamo.generate_chat_membership_user_ids_by_chat(group_chat.id)) == []
    assert list(chat_message_manager.dynamo.generate_chat_messages_by_chat(group_chat.id)) == []


def test_cant_delete_group_chat_with_members(group_chat):
    with pytest.raises(group_chat.dynamo.client.exceptions.ConditionalCheckFailedException):
        group_chat.delete_group_chat()


def test_cant_delete_group_chat_non_group_chat(direct_chat):
    with pytest.raises(AssertionError, match='non-GROUP chats'):
        direct_chat.delete_group_chat()


def test_delete_direct_chat(direct_chat, user1, user2):
    # verify user totals are as expected
    user1.refresh_item()
    user2.refresh_item()
    assert user1.item['chatCount'] == 1
    assert user2.item['chatCount'] == 1

    # verify we see the chat and chat_memberships in the DB
    assert direct_chat.dynamo.get_chat(direct_chat.id)
    assert direct_chat.dynamo.get_chat_membership(direct_chat.id, user1.id)
    assert direct_chat.dynamo.get_chat_membership(direct_chat.id, user2.id)

    # delete the chat
    direct_chat.delete_direct_chat()

    # verify user totals are as expected
    user1.refresh_item()
    user2.refresh_item()
    assert user1.item['chatCount'] == 0
    assert user2.item['chatCount'] == 0

    # verify we see the chat and chat_memberships have disapeared from DB
    assert direct_chat.dynamo.get_chat(direct_chat.id) is None
    assert direct_chat.dynamo.get_chat_membership(direct_chat.id, user1.id) is None
    assert direct_chat.dynamo.get_chat_membership(direct_chat.id, user2.id) is None


def test_cant_delete_direct_chat_non_direct_chat(group_chat):
    with pytest.raises(AssertionError, match='non-DIRECT chats'):
        group_chat.delete_direct_chat()
