import pendulum
import pytest

from app.models.chat.dynamo import ChatDynamo


@pytest.fixture
def chat_dynamo(dynamo_client):
    yield ChatDynamo(dynamo_client)


def test_transact_add_group_chat_minimal(chat_dynamo):
    chat_id = 'cid'
    chat_type = 'GROUP'
    user_id = 'cuid'

    # add the chat to the DB
    before = pendulum.now('utc')
    transact = chat_dynamo.transact_add(chat_id, chat_type, user_id)
    after = pendulum.now('utc')
    chat_dynamo.client.transact_write_items([transact])

    # retrieve the chat and verify all good
    chat_item = chat_dynamo.get(chat_id)
    created_at = pendulum.parse(chat_item['createdAt'])
    assert before <= created_at
    assert after >= created_at
    assert chat_item == {
        'partitionKey': 'chat/cid',
        'sortKey': '-',
        'schemaVersion': 0,
        'chatId': 'cid',
        'chatType': 'GROUP',
        'createdAt': created_at.to_iso8601_string(),
        'createdByUserId': 'cuid',
        'userCount': 1,
    }

    # verify we can't add another chat with same id
    with pytest.raises(chat_dynamo.client.exceptions.TransactionCanceledException):
        chat_dynamo.client.transact_write_items([transact])


def test_transact_add_group_chat_maximal(chat_dynamo):
    chat_id = 'cid'
    chat_type = 'GROUP'
    user_id = 'cuid'
    name = 'group name'

    # add the chat to the DB
    now = pendulum.now('utc')
    transact = chat_dynamo.transact_add(chat_id, chat_type, user_id, name=name, now=now)
    chat_dynamo.client.transact_write_items([transact])

    # retrieve the chat and verify all good
    chat_item = chat_dynamo.get(chat_id)
    assert chat_item == {
        'partitionKey': 'chat/cid',
        'sortKey': '-',
        'schemaVersion': 0,
        'chatId': 'cid',
        'chatType': 'GROUP',
        'createdAt': now.to_iso8601_string(),
        'createdByUserId': 'cuid',
        'userCount': 1,
        'name': 'group name'
    }

    # verify we can't add another chat with same id
    with pytest.raises(chat_dynamo.client.exceptions.TransactionCanceledException):
        chat_dynamo.client.transact_write_items([transact])


def test_transact_add_direct_chat_maximal(chat_dynamo):
    chat_id = 'cid2'
    chat_type = 'DIRECT'
    creator_user_id = 'uidb'
    with_user_id = 'uida'
    name = 'cname'
    now = pendulum.now('utc')

    # add the chat to the DB
    transact = chat_dynamo.transact_add(chat_id, chat_type, creator_user_id, with_user_id, name=name, now=now)
    chat_dynamo.client.transact_write_items([transact])

    # retrieve the chat and verify all good
    chat_item = chat_dynamo.get(chat_id)
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
        'createdByUserId': 'uidb',
    }


def test_transact_add_errors(chat_dynamo):
    with pytest.raises(AssertionError, match='require with_user_id'):
        chat_dynamo.transact_add('cid', 'DIRECT', 'uid')

    with pytest.raises(AssertionError, match='forbit with_user_id'):
        chat_dynamo.transact_add('cid', 'GROUP', 'uid', with_user_id='uid')


def test_update_name(chat_dynamo):
    chat_id = 'cid'
    chat_type = 'ctype'
    user_id = 'uid'

    # add the chat to the DB, verify it is in DB
    transact = chat_dynamo.transact_add(chat_id, chat_type, user_id)
    chat_dynamo.client.transact_write_items([transact])
    assert 'name' not in chat_dynamo.get(chat_id)

    # update the chat name to something
    chat_dynamo.update_name(chat_id, 'new name')
    assert chat_dynamo.get(chat_id)['name'] == 'new name'

    # delete the chat name
    chat_dynamo.update_name(chat_id, '')
    assert 'name' not in chat_dynamo.get(chat_id)


def test_transact_delete(chat_dynamo):
    chat_id = 'cid'
    chat_type = 'ctype'
    user_id = 'uid'

    # add the chat to the DB, verify it is in DB
    transact = chat_dynamo.transact_add(chat_id, chat_type, user_id)
    chat_dynamo.client.transact_write_items([transact])
    assert chat_dynamo.get(chat_id)

    # delete it, verify it was removed from DB
    transact = chat_dynamo.transact_delete(chat_id)
    chat_dynamo.client.transact_write_items([transact])
    assert chat_dynamo.get(chat_id) is None


def test_transact_delete_expected_user_count(chat_dynamo):
    chat_id = 'cid'
    chat_type = 'ctype'
    user_id = 'uid'

    # add the chat to the DB, verify it is in DB
    transact = chat_dynamo.transact_add(chat_id, chat_type, user_id)
    chat_dynamo.client.transact_write_items([transact])
    assert chat_dynamo.get(chat_id)['userCount'] == 1

    # verify can't deleted with wrong userCount
    transact = chat_dynamo.transact_delete(chat_id, expected_user_count=0)
    with pytest.raises(chat_dynamo.client.exceptions.TransactionCanceledException):
        chat_dynamo.client.transact_write_items([transact])

    # delete it, verify it was removed from DB
    transact = chat_dynamo.transact_delete(chat_id, expected_user_count=1)
    chat_dynamo.client.transact_write_items([transact])
    assert chat_dynamo.get(chat_id) is None


def test_increment_decrement_user_count(chat_dynamo):
    chat_id = 'cid'
    chat_type = 'ctype'
    user_id = 'uid'

    # add the chat to the DB, verify it is in DB
    transact = chat_dynamo.transact_add(chat_id, chat_type, user_id)
    chat_dynamo.client.transact_write_items([transact])
    assert chat_dynamo.get(chat_id)['userCount'] == 1

    # increment
    transacts = [chat_dynamo.transact_increment_user_count(chat_id)]
    chat_dynamo.client.transact_write_items(transacts)
    assert chat_dynamo.get(chat_id)['userCount'] == 2

    # decrement
    transacts = [chat_dynamo.transact_decrement_user_count(chat_id)]
    chat_dynamo.client.transact_write_items(transacts)
    assert chat_dynamo.get(chat_id)['userCount'] == 1

    # decrement
    transacts = [chat_dynamo.transact_decrement_user_count(chat_id)]
    chat_dynamo.client.transact_write_items(transacts)
    assert chat_dynamo.get(chat_id)['userCount'] == 0

    # verify can't go below zero
    transacts = [chat_dynamo.transact_decrement_user_count(chat_id)]
    with pytest.raises(chat_dynamo.client.exceptions.TransactionCanceledException):
        chat_dynamo.client.transact_write_items(transacts)


def test_transact_register_chat_message_added(chat_dynamo):
    chat_id = 'cid'

    # verify can't register to non-existent chat
    now = pendulum.now('utc')
    transact = chat_dynamo.transact_register_chat_message_added(chat_id, now)
    with pytest.raises(chat_dynamo.client.exceptions.TransactionCanceledException):
        chat_dynamo.client.transact_write_items([transact])

    # add a chat
    transact = chat_dynamo.transact_add(chat_id, 'ctype', 'uid')
    chat_dynamo.client.transact_write_items([transact])

    # check its starting state
    chat_item = chat_dynamo.get(chat_id)
    assert 'messageCount' not in chat_item
    assert 'lastMessageActivityAt' not in chat_item

    # register a message added
    now = pendulum.now('utc')
    transact = chat_dynamo.transact_register_chat_message_added(chat_id, now)
    chat_dynamo.client.transact_write_items([transact])

    # check state now
    new_chat_item = chat_dynamo.get(chat_id)
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
    new_chat_item = chat_dynamo.get(chat_id)
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
    with pytest.raises(chat_dynamo.client.exceptions.TransactionCanceledException):
        chat_dynamo.client.transact_write_items([transact])

    # add a chat
    transact = chat_dynamo.transact_add(chat_id, 'ctype', 'uid')
    chat_dynamo.client.transact_write_items([transact])

    # register a message added (will always happen before editing a message)
    now = pendulum.now('utc')
    transact = chat_dynamo.transact_register_chat_message_added(chat_id, now)
    chat_dynamo.client.transact_write_items([transact])

    # check its starting state
    chat_item = chat_dynamo.get(chat_id)
    assert pendulum.parse(chat_item['lastMessageActivityAt']) == now

    # register a message edited
    new_now = pendulum.now('utc')
    transact = chat_dynamo.transact_register_chat_message_edited(chat_id, new_now)
    chat_dynamo.client.transact_write_items([transact])

    # check state now
    new_chat_item = chat_dynamo.get(chat_id)
    assert pendulum.parse(new_chat_item['lastMessageActivityAt']) == new_now
    chat_item['lastMessageActivityAt'] = new_chat_item['lastMessageActivityAt']
    assert chat_item == new_chat_item


def test_transact_register_chat_message_deleted(chat_dynamo):
    chat_id = 'cid'

    # verify can't register to non-existent chat
    now = pendulum.now('utc')
    transact = chat_dynamo.transact_register_chat_message_deleted(chat_id, now)
    with pytest.raises(chat_dynamo.client.exceptions.TransactionCanceledException):
        chat_dynamo.client.transact_write_items([transact])

    # add a chat
    transact = chat_dynamo.transact_add(chat_id, 'ctype', 'uid')
    chat_dynamo.client.transact_write_items([transact])

    # register a message added (will always happen before deleting a message)
    now = pendulum.now('utc')
    transact = chat_dynamo.transact_register_chat_message_added(chat_id, now)
    chat_dynamo.client.transact_write_items([transact])

    # check its starting state
    chat_item = chat_dynamo.get(chat_id)
    assert chat_item['messageCount'] == 1
    assert pendulum.parse(chat_item['lastMessageActivityAt']) == now

    # register a message deleted
    new_now = pendulum.now('utc')
    transact = chat_dynamo.transact_register_chat_message_deleted(chat_id, new_now)
    chat_dynamo.client.transact_write_items([transact])

    # check state now
    new_chat_item = chat_dynamo.get(chat_id)
    assert new_chat_item['messageCount'] == 0
    assert pendulum.parse(new_chat_item['lastMessageActivityAt']) == new_now
    chat_item['messageCount'] = new_chat_item['messageCount']
    chat_item['lastMessageActivityAt'] = new_chat_item['lastMessageActivityAt']
    assert chat_item == new_chat_item
