import pendulum
import pytest

from app.models.chat.dynamo import ChatMemberDynamo


@pytest.fixture
def cm_dynamo(dynamo_client):
    yield ChatMemberDynamo(dynamo_client)


def test_transact_add(cm_dynamo):
    chat_id = 'cid2'
    user_id = 'uid'
    now = pendulum.now('utc')

    # add the chat membership to the DB
    transact = cm_dynamo.transact_add(chat_id, user_id, now=now)
    cm_dynamo.client.transact_write_items([transact])

    # retrieve the chat membership and verify all good
    item = cm_dynamo.get(chat_id, user_id)
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


def test_transact_delete(cm_dynamo):
    chat_id = 'cid'
    user_id = 'uid'

    # add the chat membership to the DB, verify it is in DB
    transact = cm_dynamo.transact_add(chat_id, user_id)
    cm_dynamo.client.transact_write_items([transact])
    assert cm_dynamo.get(chat_id, user_id)

    # delete it, verify it was removed from DB
    transact = cm_dynamo.transact_delete(chat_id, user_id)
    cm_dynamo.client.transact_write_items([transact])
    assert cm_dynamo.get(chat_id, user_id) is None


def test_update_last_message_activity_at(cm_dynamo):
    chat_id = 'cid'

    # add a member to the chat
    user_id = 'uid1'
    now = pendulum.now('utc')
    transact = cm_dynamo.transact_add(chat_id, user_id, now)
    cm_dynamo.client.transact_write_items([transact])

    # verify starting state
    org_item = cm_dynamo.get(chat_id, user_id)
    assert org_item['gsiK2SortKey'] == 'chat/' + now.to_iso8601_string()

    # update the last message activity at for that memeber
    new_now = pendulum.now('utc')
    item = cm_dynamo.update_last_message_activity_at(chat_id, user_id, new_now)
    assert item['gsiK2SortKey'] == 'chat/' + new_now.to_iso8601_string()

    # verify final state
    item = cm_dynamo.get(chat_id, user_id)
    assert item['gsiK2SortKey'] == 'chat/' + new_now.to_iso8601_string()
    item['gsiK2SortKey'] = org_item['gsiK2SortKey']
    assert item == org_item


def test_generate_user_ids_by_chat(cm_dynamo):
    chat_id = 'cid'

    # verify nothing from non-existent chat / chat with no members
    assert list(cm_dynamo.generate_user_ids_by_chat(chat_id)) == []

    # add a member to the chat
    user_id_1 = 'uid1'
    transact = cm_dynamo.transact_add(chat_id, user_id_1)
    cm_dynamo.client.transact_write_items([transact])

    # verify we generate that user_id
    assert list(cm_dynamo.generate_user_ids_by_chat(chat_id)) == [user_id_1]

    # add another member to the chat
    user_id_2 = 'uid2'
    transact = cm_dynamo.transact_add(chat_id, user_id_2)
    cm_dynamo.client.transact_write_items([transact])

    # verify we generate both user_ids, in order
    assert list(cm_dynamo.generate_user_ids_by_chat(chat_id)) == [user_id_1, user_id_2]


def test_generate_chat_ids_by_chat(cm_dynamo):
    user_id = 'cid'

    # verify nothing
    assert list(cm_dynamo.generate_chat_ids_by_user(user_id)) == []

    # add user to a chat
    chat_id_1 = 'cid1'
    transact = cm_dynamo.transact_add(chat_id_1, user_id)
    cm_dynamo.client.transact_write_items([transact])

    # verify we generate that chat_id
    assert list(cm_dynamo.generate_chat_ids_by_user(user_id)) == [chat_id_1]

    # add user to another chat
    chat_id_2 = 'cid2'
    transact = cm_dynamo.transact_add(chat_id_2, user_id)
    cm_dynamo.client.transact_write_items([transact])

    # verify we generate both chat_ids, in order
    assert list(cm_dynamo.generate_chat_ids_by_user(user_id)) == [chat_id_1, chat_id_2]
