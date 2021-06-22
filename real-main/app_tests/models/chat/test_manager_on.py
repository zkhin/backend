import logging
from unittest.mock import patch
from uuid import uuid4

import pendulum
import pytest


@pytest.fixture
def user1(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_user_pool_entry(user_id, username, verified_email=f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user1
user3 = user1


@pytest.fixture
def chat(chat_manager, user1, user2):
    chat_id = str(uuid4())
    chat = chat_manager.add_direct_chat(chat_id, user1.id, user2.id)
    for member_item in chat_manager.on_chat_add(chat_id, chat.item):
        chat_manager.on_chat_member_add(chat_id, member_item)
    yield chat


@pytest.fixture
def user1_message(chat_message_manager, chat, user1):
    yield chat_message_manager.add_chat_message(chat.id, 'lore', user_id=user1.id)


@pytest.fixture
def user2_message(chat_message_manager, chat, user2):
    yield chat_message_manager.add_chat_message(chat.id, 'lore', user_id=user2.id)


@pytest.fixture
def system_message(chat_message_manager, chat):
    yield chat_message_manager.add_chat_message(chat.id, 'system lore')


def test_on_chat_add_direct_chat_adds_member_items(chat_manager, user1, user3):
    chat = chat_manager.add_direct_chat(str(uuid4()), user1.id, user3.id)
    assert chat_manager.member_dynamo.get(chat.id, user1.id) is None
    assert chat_manager.member_dynamo.get(chat.id, user3.id) is None
    chat_manager.on_chat_add(chat.id, chat.item)
    assert chat_manager.member_dynamo.get(chat.id, user1.id)
    assert chat_manager.member_dynamo.get(chat.id, user3.id)


def test_on_chat_add_group_chat_minimal_adds_member_items(chat_manager, user1):
    chat = chat_manager.add_group_chat(str(uuid4()), user1.id, [])
    assert chat_manager.member_dynamo.get(chat.id, user1.id) is None
    chat_manager.on_chat_add(chat.id, chat.item)
    assert chat_manager.member_dynamo.get(chat.id, user1.id)


def test_on_chat_add_group_chat_with_user_ids_adds_member_items(chat_manager, user1, user2, user3):
    chat = chat_manager.add_group_chat(str(uuid4()), user1.id, [user2.id, user3.id])
    assert chat_manager.member_dynamo.get(chat.id, user1.id) is None
    assert chat_manager.member_dynamo.get(chat.id, user2.id) is None
    assert chat_manager.member_dynamo.get(chat.id, user3.id) is None
    chat_manager.on_chat_add(chat.id, chat.item)
    assert chat_manager.member_dynamo.get(chat.id, user1.id)
    assert chat_manager.member_dynamo.get(chat.id, user2.id)
    assert chat_manager.member_dynamo.get(chat.id, user3.id)


def test_on_chat_add_preserves_created_at(chat_manager, user1, user3):
    chat = chat_manager.add_direct_chat(str(uuid4()), user1.id, user3.id)
    chat_manager.on_chat_add(chat.id, chat.item)
    assert chat_manager.member_dynamo.get(chat.id, user1.id)['createdAt'] == chat.item['createdAt']
    assert chat_manager.member_dynamo.get(chat.id, user3.id)['createdAt'] == chat.item['createdAt']


def test_on_chat_user_count_change_throws_if_no_change(chat_manager, chat):
    with pytest.raises(AssertionError):
        chat_manager.on_chat_user_count_change(chat.id, chat.item, chat.item)
    with pytest.raises(AssertionError):
        chat_manager.on_chat_user_count_change(chat.id, chat.item, {**chat.item, 'userCount': 0})
    item = {**chat.item, 'userCount': 1}
    with pytest.raises(AssertionError):
        chat_manager.on_chat_user_count_change(chat.id, item, item)


def test_on_chat_user_count_change_does_not_hit_zero_so_no_delete(chat_manager, chat):
    assert chat.refresh_item().item
    chat_manager.on_chat_user_count_change(chat.id, {**chat.item, 'userCount': 1}, {**chat.item, 'userCount': 2})
    assert chat.refresh_item().item
    chat_manager.on_chat_user_count_change(chat.id, {**chat.item, 'userCount': 1}, {**chat.item, 'userCount': 0})
    assert chat.refresh_item().item


def test_on_chat_user_count_change_hits_zero_so_deletes(chat_manager, chat):
    assert chat.refresh_item().item
    chat_manager.on_chat_user_count_change(chat.id, {**chat.item, 'userCount': 0}, {**chat.item, 'userCount': 1})
    assert chat.refresh_item().item is None


def test_on_chat_member_add_increments_user_count(chat_manager, chat):
    assert chat.refresh_item().user_count == 2
    chat_manager.on_chat_member_add(chat.id, {})
    assert chat.refresh_item().user_count == 3
    chat_manager.on_chat_member_add(chat.id, {})
    assert chat.refresh_item().user_count == 4


def test_on_chat_member_delete_decrements_user_count(chat_manager, chat):
    assert chat.refresh_item().user_count == 2
    chat_manager.on_chat_member_delete(chat.id, {})
    assert chat.refresh_item().user_count == 1
    chat_manager.on_chat_member_delete(chat.id, {})
    assert chat.refresh_item().user_count == 0


def test_on_message_added(chat_manager, chat, user1, user2, caplog, user1_message, user2_message):
    # verify starting state
    chat.refresh_item()
    assert 'messagesCount' not in chat.item
    assert 'lastMessageActivityAt' not in chat.item
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', chat.item['createdAt']]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', chat.item['createdAt']]
    assert 'messagesUnviewedCount' not in user1_member_item
    assert 'messagesUnviewedCount' not in user2_member_item

    # react to adding a message by user1, verify state
    now = user1_message.created_at
    chat_manager.on_chat_message_add(user1_message.id, new_item=user1_message.item)
    chat.refresh_item()
    assert chat.item['messagesCount'] == 1
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert 'messagesUnviewedCount' not in user1_member_item
    assert user2_member_item['messagesUnviewedCount'] == 1

    # react to adding a message by user2, verify state
    now = user2_message.created_at
    chat_manager.on_chat_message_add(user2_message.id, new_item=user2_message.item)
    chat.refresh_item()
    assert chat.item['messagesCount'] == 2
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user1_member_item['messagesUnviewedCount'] == 1
    assert user2_member_item['messagesUnviewedCount'] == 1

    # react to adding a another message by user2 out of order
    new_item = {
        **user2_message.item,
        'createdAt': user2_message.created_at.subtract(seconds=5).to_iso8601_string(),
    }
    with caplog.at_level(logging.WARNING):
        chat_manager.on_chat_message_add(user2_message.id, new_item=new_item)
    assert len(caplog.records) == 3
    assert all('Failed' in rec.msg for rec in caplog.records)
    assert all('last message activity' in rec.msg for rec in caplog.records)
    assert all(chat.id in rec.msg for rec in caplog.records)
    uid1, uid2 = sorted([user1.id, user2.id])
    assert uid1 in caplog.records[1].msg
    assert uid2 in caplog.records[2].msg

    # verify final state
    chat.refresh_item()
    assert chat.item['messagesCount'] == 3
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user1_member_item['messagesUnviewedCount'] == 2
    assert user2_member_item['messagesUnviewedCount'] == 1


def test_on_message_added_system_message(chat_manager, chat, user1, user2, system_message):
    # verify starting state
    chat.refresh_item()
    assert 'messagesCount' not in chat.item
    assert 'lastMessageActivityAt' not in chat.item
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', chat.item['createdAt']]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', chat.item['createdAt']]
    assert 'messagesUnviewedCount' not in user1_member_item
    assert 'messagesUnviewedCount' not in user2_member_item

    # react to adding a message by the system, verify state
    now = system_message.created_at
    chat_manager.on_chat_message_add(system_message.id, new_item=system_message.item)
    chat.refresh_item()
    assert chat.item['messagesCount'] == 1
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    user1_member_item = chat.member_dynamo.get(chat.id, user1.id)
    user2_member_item = chat.member_dynamo.get(chat.id, user2.id)
    assert user1_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user2_member_item['gsiK2SortKey'].split('/') == ['chat', now.to_iso8601_string()]
    assert user1_member_item['messagesUnviewedCount'] == 1
    assert user2_member_item['messagesUnviewedCount'] == 1


def test_on_chat_message_delete(chat_manager, chat, user1, user2, caplog, user1_message):
    # reacht to an add to increment counts, and verify starting state
    chat_manager.on_chat_message_add(user1_message.id, new_item=user1_message.item)
    assert chat.refresh_item().item['messagesCount'] == 1
    assert chat.member_dynamo.get(chat.id, user1.id).get('messagesUnviewedCount', 0) == 0
    assert chat.member_dynamo.get(chat.id, user2.id).get('messagesUnviewedCount', 0) == 1

    # react to a message delete, verify counts drop as expected
    chat_manager.on_chat_message_delete(user1_message.id, old_item=user1_message.item)
    assert chat.refresh_item().item['messagesCount'] == 0
    assert chat.member_dynamo.get(chat.id, user1.id).get('messagesUnviewedCount', 0) == 0
    assert chat.member_dynamo.get(chat.id, user2.id).get('messagesUnviewedCount', 0) == 0

    # react to a message delete, verify fails softly and final state
    with caplog.at_level(logging.WARNING):
        chat_manager.on_chat_message_delete(user1_message.id, old_item=user1_message.item)
    assert len(caplog.records) == 2
    assert 'Failed to decrement messagesCount' in caplog.records[0].msg
    assert 'Failed to decrement messagesUnviewedCount' in caplog.records[1].msg
    assert chat.id in caplog.records[0].msg
    assert chat.id in caplog.records[1].msg
    assert chat.refresh_item().item['messagesCount'] == 0
    assert chat.member_dynamo.get(chat.id, user1.id).get('messagesUnviewedCount', 0) == 0
    assert chat.member_dynamo.get(chat.id, user2.id).get('messagesUnviewedCount', 0) == 0


def test_on_message_delete_handles_chat_views_correctly(chat, user1, user2, chat_message_manager, chat_manager):
    # each user posts two messages, one of which is 'viewed' by both and the other is not
    message1 = chat_message_manager.add_chat_message(chat.id, 'lore ipsum', user_id=user1.id)
    message2 = chat_message_manager.add_chat_message(chat.id, 'lore ipsum', user_id=user2.id)
    chat_manager.on_chat_message_add(message1.id, new_item=message1.item)
    chat_manager.on_chat_message_add(message1.id, new_item=message1.item)

    chat_manager.record_views([chat.id], user1.id)
    chat_manager.record_views([chat.id], user2.id)
    chat_manager.member_dynamo.clear_messages_unviewed_count(chat.id, user1.id)
    chat_manager.member_dynamo.clear_messages_unviewed_count(chat.id, user2.id)

    message3 = chat_message_manager.add_chat_message(chat.id, 'lore ipsum', user_id=user1.id)
    message4 = chat_message_manager.add_chat_message(chat.id, 'lore ipsum', user_id=user2.id)
    chat_manager.on_chat_message_add(message3.id, new_item=message3.item)
    chat_manager.on_chat_message_add(message4.id, new_item=message4.item)

    # verify starting state
    chat.refresh_item()
    assert chat.item['messagesCount'] == 4
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == message4.created_at
    assert chat.member_dynamo.get(chat.id, user1.id)['messagesUnviewedCount'] == 1
    assert chat.member_dynamo.get(chat.id, user2.id)['messagesUnviewedCount'] == 1

    # react to deleting message2, check counts
    chat_manager.on_chat_message_delete(message2.id, old_item=message2.item)
    assert chat.refresh_item().item['messagesCount'] == 3
    assert chat.member_dynamo.get(chat.id, user1.id)['messagesUnviewedCount'] == 1
    assert chat.member_dynamo.get(chat.id, user2.id)['messagesUnviewedCount'] == 1

    # react to deleting message3, check counts
    chat_manager.on_chat_message_delete(message3.id, old_item=message3.item)
    assert chat.refresh_item().item['messagesCount'] == 2
    assert chat.member_dynamo.get(chat.id, user1.id)['messagesUnviewedCount'] == 1
    assert chat.member_dynamo.get(chat.id, user2.id)['messagesUnviewedCount'] == 0

    # react to deleting message1, check counts
    chat_manager.on_chat_message_delete(message1.id, old_item=message1.item)
    assert chat.refresh_item().item['messagesCount'] == 1
    assert chat.member_dynamo.get(chat.id, user1.id)['messagesUnviewedCount'] == 1
    assert chat.member_dynamo.get(chat.id, user2.id)['messagesUnviewedCount'] == 0

    # react to deleting message4, check counts
    chat_manager.on_chat_message_delete(message4.id, old_item=message4.item)
    assert chat.refresh_item().item['messagesCount'] == 0
    assert chat.member_dynamo.get(chat.id, user1.id)['messagesUnviewedCount'] == 0
    assert chat.member_dynamo.get(chat.id, user2.id)['messagesUnviewedCount'] == 0


def test_on_flag_add_deletes_chat_if_crowdsourced_criteria_met(chat_manager, chat, user2):
    # react to a flagging without meeting the criteria, verify doesn't delete
    with patch.object(chat, 'is_crowdsourced_forced_removal_criteria_met', return_value=False):
        with patch.object(chat_manager, 'init_chat', return_value=chat):
            chat_manager.on_flag_add(chat.id, new_item={})
    assert chat.refresh_item().item

    # react to a flagging with meeting the criteria, verify deletes
    with patch.object(chat, 'is_crowdsourced_forced_removal_criteria_met', return_value=True):
        with patch.object(chat_manager, 'init_chat', return_value=chat):
            chat_manager.on_flag_add(chat.id, new_item={})
    assert chat.refresh_item().item is None


def test_on_chat_message_flag_add_chat_message_flag(chat_manager, user1_message, user1):
    # check & configure starting state
    assert user1_message.refresh_item().item.get('flagCount', 0) == 0
    for _ in range(8):
        user1_message.chat.dynamo.increment_user_count(user1_message.chat_id)
    assert user1_message.chat.refresh_item().item['userCount'] == 10  # just above cutoff for one flag

    # messageprocess, verify flagCount is incremented & not force achived
    chat_manager.on_chat_message_flag_add(user1_message.id, new_item={'sortKey': f'flag/{user1.id}'})
    assert user1_message.refresh_item().item.get('flagCount', 0) == 1


def test_on_chat_message_flag_add_chat_message_force_delete_by_crowdsourced_criteria(
    chat_manager, user1_message, user1, user2, caplog
):
    # configure and check starting state
    assert user1_message.refresh_item().item.get('flagCount', 0) == 0
    for _ in range(7):
        user1_message.chat.dynamo.increment_user_count(user1_message.chat_id)
    assert user1_message.chat.refresh_item().item['userCount'] == 9  # just below 10% cutoff for one flag

    # postprocess, verify flagCount is incremented and force archived
    chat_manager.on_chat_message_flag_add(user1_message.id, new_item={'sortKey': f'flag/{user1.id}'})
    with caplog.at_level(logging.WARNING):
        chat_manager.on_chat_message_flag_add(user1_message.id, new_item={'sortKey': f'flag/{user2.id}'})
    assert len(caplog.records) == 1
    assert 'Force deleting chat message' in caplog.records[0].msg
    assert user1_message.refresh_item().item is None


def test_on_chat_message_flag_add_chat_flag(chat_manager, chat_message_manager, chat, user1, user2):
    user2_message_1 = chat_message_manager.add_chat_message(chat.id, 'lore', user_id=user2.id)
    user2_message_2 = chat_message_manager.add_chat_message(chat.id, 'lore', user_id=user2.id)
    # check starting state
    assert chat.flag_dynamo.get(chat.id, user1.id) is None

    # user1 flags user2's chat message first time
    chat_manager.on_chat_message_flag_add(user2_message_1.id, new_item={'sortKey': f'flag/{user1.id}'})
    assert chat.flag_dynamo.get(chat.id, user1.id)

    # user1 flags user2's chat message again
    chat_manager.on_chat_message_flag_add(user2_message_2.id, new_item={'sortKey': f'flag/{user1.id}'})
    assert chat.flag_dynamo.get(chat.id, user1.id)
    # check chat is force deleted
    assert chat_manager.get_chat(chat.id) is None


def test_on_chat_delete_delete_memberships(chat_manager, user1, user2, chat):
    # set up a group chat as well, add both users, verify starting state
    group_chat = chat_manager.add_group_chat(str(uuid4()), user1.id, [user2.id])
    chat_manager.on_chat_add(group_chat.id, group_chat.item)
    assert sum(1 for _ in chat_manager.member_dynamo.generate_chat_ids_by_user(user1.id)) == 2
    assert sum(1 for _ in chat_manager.member_dynamo.generate_chat_ids_by_user(user2.id)) == 2

    # react to the delete of one of the chats, verify state
    chat_manager.on_chat_delete_delete_memberships(chat.id, old_item=chat.item)
    assert sum(1 for _ in chat_manager.member_dynamo.generate_chat_ids_by_user(user1.id)) == 1
    assert sum(1 for _ in chat_manager.member_dynamo.generate_chat_ids_by_user(user2.id)) == 1

    # react to the delete of the other chat, verify state
    chat_manager.on_chat_delete_delete_memberships(group_chat.id, old_item=group_chat.item)
    assert sum(1 for _ in chat_manager.member_dynamo.generate_chat_ids_by_user(user1.id)) == 0
    assert sum(1 for _ in chat_manager.member_dynamo.generate_chat_ids_by_user(user2.id)) == 0


def test_on_user_delete_leave_all_chats(chat_manager, user1, user2, user3):
    chat_id_1 = 'cid1'
    chat_id_2 = 'cid2'
    chat_id_3 = 'cid3'
    chat_id_4 = 'cid4'
    # user1 opens up direct chats with both of the other two users
    # user1 sets up a group chat with only themselves in it, and another with user2
    chat1 = chat_manager.add_direct_chat(chat_id_1, user1.id, user2.id)
    chat2 = chat_manager.add_direct_chat(chat_id_2, user1.id, user3.id)
    chat3 = chat_manager.add_group_chat(chat_id_3, user1.id, [])
    chat4 = chat_manager.add_group_chat(chat_id_4, user1.id, [user2.id])
    for member_item in chat_manager.on_chat_add(chat_id_1, chat1.item):
        chat_manager.on_chat_member_add(chat_id_1, member_item)
    for member_item in chat_manager.on_chat_add(chat_id_2, chat2.item):
        chat_manager.on_chat_member_add(chat_id_2, member_item)
    for member_item in chat_manager.on_chat_add(chat_id_3, chat3.item):
        chat_manager.on_chat_member_add(chat_id_3, member_item)
    for member_item in chat_manager.on_chat_add(chat_id_4, chat4.item):
        chat_manager.on_chat_member_add(chat_id_4, member_item)

    # verify we see the chat and chat_memberships in the DB
    assert chat_manager.dynamo.get(chat_id_1)['userCount'] == 2
    assert chat_manager.dynamo.get(chat_id_2)['userCount'] == 2
    assert chat_manager.dynamo.get(chat_id_3)['userCount'] == 1
    assert chat_manager.dynamo.get(chat_id_4)['userCount'] == 2
    assert chat_manager.member_dynamo.get(chat_id_1, user1.id)
    assert chat_manager.member_dynamo.get(chat_id_1, user2.id)
    assert chat_manager.member_dynamo.get(chat_id_2, user1.id)
    assert chat_manager.member_dynamo.get(chat_id_2, user3.id)
    assert chat_manager.member_dynamo.get(chat_id_3, user1.id)
    assert chat_manager.member_dynamo.get(chat_id_4, user1.id)
    assert chat_manager.member_dynamo.get(chat_id_4, user2.id)

    # user1 leaves all their chats, which should trigger deletes of both direct chats
    chat_manager.on_user_delete_leave_all_chats(user1.id, old_item=user1.item)

    # verify we see the chat and chat_memberships in the DB
    assert chat_manager.dynamo.get(chat_id_1) is None
    assert chat_manager.dynamo.get(chat_id_2) is None
    assert chat3.is_member(user1.id) is False
    assert chat4.is_member(user1.id) is False
