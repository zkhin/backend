import logging
from uuid import uuid4

import pendulum
import pytest

from app.models.chat.dynamo import ChatDynamo
from app.models.chat.enums import ChatType
from app.models.chat.exceptions import ChatAlreadyExists


@pytest.fixture
def chat_dynamo(dynamo_client):
    yield ChatDynamo(dynamo_client)


@pytest.mark.parametrize('with_user_ids', [[], ['wuid1', 'wuid2']])
def test_add_error_direct_chat_number_of_participants(chat_dynamo, with_user_ids):
    with pytest.raises(AssertionError, match='DIRECT chats require exactly two participants'):
        chat_dynamo.add('cid', ChatType.DIRECT, 'uid1', with_user_ids, 'mtxt')


def test_add_error_direct_chat_name(chat_dynamo):
    with pytest.raises(AssertionError, match='DIRECT chats cannot be named'):
        chat_dynamo.add('cid', ChatType.DIRECT, 'uid1', ['uid2'], 'mtxt', name='anything')


def test_cant_add_same_group_chat_twice(chat_dynamo):
    chat_id = str(uuid4())
    chat_dynamo.add(chat_id, ChatType.GROUP, str(uuid4()), [], str(uuid4()))
    with pytest.raises(ChatAlreadyExists, match=chat_id):
        chat_dynamo.add(chat_id, ChatType.GROUP, str(uuid4()), [], str(uuid4()))


def test_add_group_chat_minimal(chat_dynamo):
    chat_id, user_id, msg_txt = str(uuid4()), str(uuid4()), str(uuid4())
    before = pendulum.now('utc')
    chat_item = chat_dynamo.add(chat_id, ChatType.GROUP, user_id, [], msg_txt)
    after = pendulum.now('utc')
    assert chat_item == chat_dynamo.get(chat_id)
    assert before <= pendulum.parse(chat_item['createdAt']) <= after
    assert chat_item == {
        'partitionKey': f'chat/{chat_id}',
        'sortKey': '-',
        'schemaVersion': 0,
        'chatId': chat_id,
        'chatType': ChatType.GROUP,
        'createdAt': chat_item['createdAt'],
        'createdByUserId': user_id,
        'initialMemberUserIds': [user_id],
        'initialMessageText': msg_txt,
    }


def test_add_group_chat_maximal(chat_dynamo):
    chat_id, user_id, with_user_id_1, with_user_id_2 = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
    msg_id, msg_txt, name = str(uuid4()), str(uuid4()), str(uuid4())
    now = pendulum.now('utc')
    chat_item = chat_dynamo.add(
        chat_id,
        ChatType.GROUP,
        user_id,
        [with_user_id_1, with_user_id_2],
        msg_txt,
        initial_message_id=msg_id,
        name=name,
        now=now,
    )
    assert chat_item == chat_dynamo.get(chat_id)
    assert chat_item == {
        'partitionKey': f'chat/{chat_id}',
        'sortKey': '-',
        'schemaVersion': 0,
        'chatId': chat_id,
        'chatType': ChatType.GROUP,
        'createdAt': now.to_iso8601_string(),
        'createdByUserId': user_id,
        'initialMemberUserIds': sorted([user_id, with_user_id_1, with_user_id_2]),
        'initialMessageId': msg_id,
        'initialMessageText': msg_txt,
        'name': name,
    }


def test_add_direct_chat(chat_dynamo):
    chat_id, user_id, user_id_2 = str(uuid4()), str(uuid4()), str(uuid4())
    msg_id, msg_txt = str(uuid4()), str(uuid4())
    sorted_user_ids = sorted([user_id, user_id_2])
    chat_item = chat_dynamo.add(
        chat_id,
        ChatType.DIRECT,
        user_id,
        [user_id_2],
        msg_txt,
        initial_message_id=msg_id,
    )
    assert chat_item == chat_dynamo.get(chat_id)
    assert chat_item == {
        'partitionKey': f'chat/{chat_id}',
        'sortKey': '-',
        'schemaVersion': 0,
        'gsiA1PartitionKey': 'chat/' + '/'.join(sorted_user_ids),
        'gsiA1SortKey': '-',
        'chatId': chat_id,
        'chatType': ChatType.DIRECT,
        'createdAt': chat_item['createdAt'],
        'createdByUserId': user_id,
        'initialMemberUserIds': sorted_user_ids,
        'initialMessageId': msg_id,
        'initialMessageText': msg_txt,
    }


def test_update_name(chat_dynamo):
    chat_id = 'cid'

    # add the chat to the DB, verify it is in DB
    chat_dynamo.add(chat_id, 'chat-type', str(uuid4()), [str(uuid4())], str(uuid4()))
    assert 'name' not in chat_dynamo.get(chat_id)

    # update the chat name to something
    chat_dynamo.update_name(chat_id, 'new name')
    assert chat_dynamo.get(chat_id)['name'] == 'new name'

    # delete the chat name
    chat_dynamo.update_name(chat_id, '')
    assert 'name' not in chat_dynamo.get(chat_id)


def test_delete(chat_dynamo):
    chat_id = 'cid'

    # add the chat to the DB, verify it is in DB
    chat_dynamo.add(chat_id, 'chat-type', str(uuid4()), [str(uuid4())], str(uuid4()))
    assert chat_dynamo.get(chat_id)

    # delete it, verify it was removed from DB
    assert chat_dynamo.delete(chat_id)
    assert chat_dynamo.get(chat_id) is None


def test_update_last_message_activity_at(chat_dynamo, caplog):
    # add the chat to the DB, verify it is in DB
    chat_id = str(uuid4())
    chat_dynamo.add(chat_id, 'chat-type', str(uuid4()), [str(uuid4())], str(uuid4()))
    assert 'lastMessageActivityAt' not in chat_dynamo.get(chat_id)

    # verify we can update from not set
    now = pendulum.now('utc')
    assert (
        pendulum.parse(chat_dynamo.update_last_message_activity_at(chat_id, now)['lastMessageActivityAt']) == now
    )
    assert pendulum.parse(chat_dynamo.get(chat_id)['lastMessageActivityAt']) == now

    # verify we can update from set
    now = pendulum.now('utc')
    assert (
        pendulum.parse(chat_dynamo.update_last_message_activity_at(chat_id, now)['lastMessageActivityAt']) == now
    )
    assert pendulum.parse(chat_dynamo.get(chat_id)['lastMessageActivityAt']) == now

    # verify we fail soft
    before = now.subtract(seconds=10)
    with caplog.at_level(logging.WARNING):
        resp = chat_dynamo.update_last_message_activity_at(chat_id, before)
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == 'WARNING'
    assert all(
        x in caplog.records[0].msg
        for x in ['Failed', 'last message activity', chat_id, before.to_iso8601_string()]
    )
    assert resp is None
    assert pendulum.parse(chat_dynamo.get(chat_id)['lastMessageActivityAt']) == now


@pytest.mark.parametrize(
    'incrementor_name, decrementor_name, attribute_name',
    [
        ['increment_flag_count', 'decrement_flag_count', 'flagCount'],
        ['increment_messages_count', 'decrement_messages_count', 'messagesCount'],
        ['increment_user_count', 'decrement_user_count', 'userCount'],
    ],
)
def test_increment_decrement_count(chat_dynamo, caplog, incrementor_name, decrementor_name, attribute_name):
    incrementor = getattr(chat_dynamo, incrementor_name)
    decrementor = getattr(chat_dynamo, decrementor_name) if decrementor_name else None
    chat_id = str(uuid4())

    # can't increment message that doesnt exist
    with caplog.at_level(logging.WARNING):
        assert incrementor(chat_id) is None
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == 'WARNING'
    assert all(x in caplog.records[0].msg for x in ['Failed to increment', attribute_name, chat_id])
    caplog.clear()

    # can't decrement message that doesnt exist
    if decrementor:
        with caplog.at_level(logging.WARNING):
            assert decrementor(chat_id) is None
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == 'WARNING'
        assert all(x in caplog.records[0].msg for x in ['Failed to decrement', attribute_name, chat_id])
        caplog.clear()

    # add the user to the DB, verify it is in DB
    chat_dynamo.add(chat_id, 'chat-type', str(uuid4()), [str(uuid4())], str(uuid4()))
    assert attribute_name not in chat_dynamo.get(chat_id)

    # increment twice, verify
    assert incrementor(chat_id)[attribute_name] == 1
    assert chat_dynamo.get(chat_id)[attribute_name] == 1
    assert incrementor(chat_id)[attribute_name] == 2
    assert chat_dynamo.get(chat_id)[attribute_name] == 2

    # all done if there's no decrementor method
    if not decrementor:
        return

    # decrement twice, verify
    assert decrementor(chat_id)[attribute_name] == 1
    assert chat_dynamo.get(chat_id)[attribute_name] == 1
    assert decrementor(chat_id)[attribute_name] == 0
    assert chat_dynamo.get(chat_id)[attribute_name] == 0

    # verify fail soft on trying to decrement below zero
    with caplog.at_level(logging.WARNING):
        resp = decrementor(chat_id)
    assert resp is None
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == 'WARNING'
    assert all(x in caplog.records[0].msg for x in ['Failed to decrement', attribute_name, chat_id])
    assert chat_dynamo.get(chat_id)[attribute_name] == 0
