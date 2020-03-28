import pendulum
import pytest

from app.models.chat.dynamo import ChatDynamo


@pytest.fixture
def chat_dynamo(dynamo_client):
    yield ChatDynamo(dynamo_client)


def test_transact_add_chat_minimal(chat_dynamo):
    chat_id = 'cid'
    chat_type = 'ctype'

    # add the chat to the DB
    before = pendulum.now('utc')
    transact = chat_dynamo.transact_add_chat(chat_id, chat_type)
    after = pendulum.now('utc')
    chat_dynamo.client.transact_write_items([transact])

    # retrieve the chat and verify all good
    chat_item = chat_dynamo.get_chat(chat_id)
    created_at = pendulum.parse(chat_item['createdAt'])
    assert before <= created_at
    assert after >= created_at
    assert chat_item == {
        'partitionKey': 'chat/cid',
        'sortKey': '-',
        'schemaVersion': 0,
        'chatId': 'cid',
        'chatType': 'ctype',
        'createdAt': created_at.to_iso8601_string(),
    }

    # verify we can't add another chat with same id
    with pytest.raises(chat_dynamo.client.exceptions.ConditionalCheckFailedException):
        chat_dynamo.client.transact_write_items([transact])


def test_transact_add_chat_maximal(chat_dynamo):
    chat_id = 'cid2'
    chat_type = 'DIRECT'
    user_ids = ['uidb', 'uida']
    name = 'cname'
    now = pendulum.now('utc')

    # add the chat to the DB
    transact = chat_dynamo.transact_add_chat(chat_id, chat_type, user_ids=user_ids, name=name, now=now)
    chat_dynamo.client.transact_write_items([transact])

    # retrieve the chat and verify all good
    chat_item = chat_dynamo.get_chat(chat_id)
    assert chat_item == {
        'partitionKey': 'chat/cid2',
        'sortKey': '-',
        'schemaVersion': 0,
        'gsiA1PartitionKey': 'chat/uida/uidb',
        'gsiA1SortKey': '-',
        'chatId': 'cid2',
        'chatType': 'DIRECT',
        'name': 'cname',
        'userCount': 2,
        'createdAt': now.to_iso8601_string(),
    }


def test_transact_add_chat_errors(chat_dynamo):
    with pytest.raises(AssertionError, match='require user_ids'):
        chat_dynamo.transact_add_chat('cid', 'DIRECT')

    with pytest.raises(AssertionError, match='forbit user_ids'):
        chat_dynamo.transact_add_chat('cid', 'GROUP', user_ids=[])


def test_transact_delete_chat(chat_dynamo):
    chat_id = 'cid'
    chat_type = 'ctype'

    # add the chat to the DB, verify it is in DB
    transact = chat_dynamo.transact_add_chat(chat_id, chat_type)
    chat_dynamo.client.transact_write_items([transact])
    assert chat_dynamo.get_chat(chat_id)

    # delete it, verify it was removed from DB
    transact = chat_dynamo.transact_delete_chat(chat_id)
    chat_dynamo.client.transact_write_items([transact])
    assert chat_dynamo.get_chat(chat_id) is None


def test_transact_add_chat_membership(chat_dynamo):
    chat_id = 'cid2'
    user_id = 'uid'
    now = pendulum.now('utc')

    # add the chat membership to the DB
    transact = chat_dynamo.transact_add_chat_membership(chat_id, user_id, now=now)
    chat_dynamo.client.transact_write_items([transact])

    # retrieve the chat membership and verify all good
    item = chat_dynamo.get_chat_membership(chat_id, user_id)
    joined_at_str = now.to_iso8601_string()
    assert item == {
        'partitionKey': 'chat/cid2',
        'sortKey': 'member/uid',
        'schemaVersion': 0,
        'gsiK1PartitionKey': 'chat/cid2',
        'gsiK1SortKey': f'member/{joined_at_str}',
        'gsiK2PartitionKey': 'member/uid',
        'gsiK2SortKey': f'chat/{joined_at_str}',
    }


def test_transact_delete_chat_membership(chat_dynamo):
    chat_id = 'cid'
    user_id = 'uid'

    # add the chat membership to the DB, verify it is in DB
    transact = chat_dynamo.transact_add_chat_membership(chat_id, user_id)
    chat_dynamo.client.transact_write_items([transact])
    assert chat_dynamo.get_chat_membership(chat_id, user_id)

    # delete it, verify it was removed from DB
    transact = chat_dynamo.transact_delete_chat_membership(chat_id, user_id)
    chat_dynamo.client.transact_write_items([transact])
    assert chat_dynamo.get_chat_membership(chat_id, user_id) is None


def test_transact_register_chat_message_added(chat_dynamo):
    chat_id = 'cid'

    # verify can't register to non-existent chat
    now = pendulum.now('utc')
    transact = chat_dynamo.transact_register_chat_message_added(chat_id, now)
    with pytest.raises(chat_dynamo.client.exceptions.ConditionalCheckFailedException):
        chat_dynamo.client.transact_write_items([transact])

    # add a chat
    transact = chat_dynamo.transact_add_chat(chat_id, 'ctype')
    chat_dynamo.client.transact_write_items([transact])

    # check its starting state
    chat_item = chat_dynamo.get_chat(chat_id)
    assert 'messageCount' not in chat_item
    assert 'lastMessageActivityAt' not in chat_item

    # register a message added
    now = pendulum.now('utc')
    transact = chat_dynamo.transact_register_chat_message_added(chat_id, now)
    chat_dynamo.client.transact_write_items([transact])

    # check state now
    new_chat_item = chat_dynamo.get_chat(chat_id)
    assert new_chat_item['messageCount'] == 1
    assert pendulum.parse(new_chat_item['lastMessageActivityAt']) == now
    chat_item['messageCount'] = new_chat_item['messageCount']
    chat_item['lastMessageActivityAt'] = new_chat_item['lastMessageActivityAt']
    assert chat_item == new_chat_item

    # register another message added
    now = pendulum.now('utc')
    transact = chat_dynamo.transact_register_chat_message_added(chat_id, now)
    chat_dynamo.client.transact_write_items([transact])

    # check state now
    new_chat_item = chat_dynamo.get_chat(chat_id)
    assert new_chat_item['messageCount'] == 2
    assert pendulum.parse(new_chat_item['lastMessageActivityAt']) == now
    chat_item['messageCount'] = new_chat_item['messageCount']
    chat_item['lastMessageActivityAt'] = new_chat_item['lastMessageActivityAt']
    assert chat_item == new_chat_item


def test_transact_register_chat_message_edited(chat_dynamo):
    chat_id = 'cid'

    # verify can't register to non-existent chat
    now = pendulum.now('utc')
    transact = chat_dynamo.transact_register_chat_message_edited(chat_id, now)
    with pytest.raises(chat_dynamo.client.exceptions.ConditionalCheckFailedException):
        chat_dynamo.client.transact_write_items([transact])

    # add a chat
    transact = chat_dynamo.transact_add_chat(chat_id, 'ctype')
    chat_dynamo.client.transact_write_items([transact])

    # register a message added (will always happen before editing a message)
    now = pendulum.now('utc')
    transact = chat_dynamo.transact_register_chat_message_added(chat_id, now)
    chat_dynamo.client.transact_write_items([transact])

    # check its starting state
    chat_item = chat_dynamo.get_chat(chat_id)
    assert pendulum.parse(chat_item['lastMessageActivityAt']) == now

    # register a message edited
    new_now = pendulum.now('utc')
    transact = chat_dynamo.transact_register_chat_message_edited(chat_id, new_now)
    chat_dynamo.client.transact_write_items([transact])

    # check state now
    new_chat_item = chat_dynamo.get_chat(chat_id)
    assert pendulum.parse(new_chat_item['lastMessageActivityAt']) == new_now
    chat_item['lastMessageActivityAt'] = new_chat_item['lastMessageActivityAt']
    assert chat_item == new_chat_item


def test_transact_register_chat_message_deleted(chat_dynamo):
    chat_id = 'cid'

    # verify can't register to non-existent chat
    now = pendulum.now('utc')
    transact = chat_dynamo.transact_register_chat_message_deleted(chat_id, now)
    with pytest.raises(chat_dynamo.client.exceptions.ConditionalCheckFailedException):
        chat_dynamo.client.transact_write_items([transact])

    # add a chat
    transact = chat_dynamo.transact_add_chat(chat_id, 'ctype')
    chat_dynamo.client.transact_write_items([transact])

    # register a message added (will always happen before deleting a message)
    now = pendulum.now('utc')
    transact = chat_dynamo.transact_register_chat_message_added(chat_id, now)
    chat_dynamo.client.transact_write_items([transact])

    # check its starting state
    chat_item = chat_dynamo.get_chat(chat_id)
    assert chat_item['messageCount'] == 1
    assert pendulum.parse(chat_item['lastMessageActivityAt']) == now

    # register a message deleted
    new_now = pendulum.now('utc')
    transact = chat_dynamo.transact_register_chat_message_deleted(chat_id, new_now)
    chat_dynamo.client.transact_write_items([transact])

    # check state now
    new_chat_item = chat_dynamo.get_chat(chat_id)
    assert new_chat_item['messageCount'] == 0
    assert pendulum.parse(new_chat_item['lastMessageActivityAt']) == new_now
    chat_item['messageCount'] = new_chat_item['messageCount']
    chat_item['lastMessageActivityAt'] = new_chat_item['lastMessageActivityAt']
    assert chat_item == new_chat_item


def test_update_chat_membership_last_message_activity_at(chat_dynamo):
    chat_id = 'cid'

    # add a member to the chat
    user_id = 'uid1'
    now = pendulum.now('utc')
    transact = chat_dynamo.transact_add_chat_membership(chat_id, user_id, now)
    chat_dynamo.client.transact_write_items([transact])

    # verify starting state
    org_item = chat_dynamo.get_chat_membership(chat_id, user_id)
    assert org_item['gsiK2SortKey'] == 'chat/' + now.to_iso8601_string()

    # update the last message activity at for that memeber
    new_now = pendulum.now('utc')
    item = chat_dynamo.update_chat_membership_last_message_activity_at(chat_id, user_id, new_now)
    assert item['gsiK2SortKey'] == 'chat/' + new_now.to_iso8601_string()

    # verify final state
    item = chat_dynamo.get_chat_membership(chat_id, user_id)
    assert item['gsiK2SortKey'] == 'chat/' + new_now.to_iso8601_string()
    item['gsiK2SortKey'] = org_item['gsiK2SortKey']
    assert item == org_item


def test_generate_chat_membership_user_ids_by_chat(chat_dynamo):
    chat_id = 'cid'

    # verify nothing from non-existent chat / chat with no members
    assert list(chat_dynamo.generate_chat_membership_user_ids_by_chat(chat_id)) == []

    # add a member to the chat
    user_id_1 = 'uid1'
    transact = chat_dynamo.transact_add_chat_membership(chat_id, user_id_1)
    chat_dynamo.client.transact_write_items([transact])

    # verify we generate that user_id
    assert list(chat_dynamo.generate_chat_membership_user_ids_by_chat(chat_id)) == [user_id_1]

    # add another member to the chat
    user_id_2 = 'uid2'
    transact = chat_dynamo.transact_add_chat_membership(chat_id, user_id_2)
    chat_dynamo.client.transact_write_items([transact])

    # verify we generate both user_ids, in order
    assert list(chat_dynamo.generate_chat_membership_user_ids_by_chat(chat_id)) == [user_id_1, user_id_2]


def test_generate_chat_membership_chat_ids_by_chat(chat_dynamo):
    user_id = 'cid'

    # verify nothing
    assert list(chat_dynamo.generate_chat_membership_chat_ids_by_user(user_id)) == []

    # add user to a chat
    chat_id_1 = 'cid1'
    transact = chat_dynamo.transact_add_chat_membership(chat_id_1, user_id)
    chat_dynamo.client.transact_write_items([transact])

    # verify we generate that chat_id
    assert list(chat_dynamo.generate_chat_membership_chat_ids_by_user(user_id)) == [chat_id_1]

    # add user to another chat
    chat_id_2 = 'cid2'
    transact = chat_dynamo.transact_add_chat_membership(chat_id_2, user_id)
    chat_dynamo.client.transact_write_items([transact])

    # verify we generate both chat_ids, in order
    assert list(chat_dynamo.generate_chat_membership_chat_ids_by_user(user_id)) == [chat_id_1, chat_id_2]
