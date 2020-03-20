import pendulum
import pytest

from app.models.chat_message.dynamo import ChatMessageDynamo


@pytest.fixture
def chat_message_dynamo(dynamo_client):
    yield ChatMessageDynamo(dynamo_client)


def test_transact_add_chat_message(chat_message_dynamo):
    message_id = 'mid'
    chat_id = 'cid'
    user_id = 'uid'
    text = 'message_text'
    text_tags = [
        {'tag': '@1', 'userId': 'uidt1'},
        {'tag': '@2', 'userId': 'uidt2'},
    ]

    # add the chat to the DB
    before = pendulum.now('utc')
    transact = chat_message_dynamo.transact_add_chat_message(message_id, chat_id, user_id, text, text_tags)
    after = pendulum.now('utc')
    chat_message_dynamo.client.transact_write_items([transact])

    # retrieve the message and verify all good
    item = chat_message_dynamo.get_chat_message(message_id)
    created_at = pendulum.parse(item['createdAt'])
    assert before <= created_at
    assert after >= created_at
    assert item == {
        'partitionKey': 'chatMessage/mid',
        'sortKey': '-',
        'schemaVersion': 0,
        'gsiA1PartitionKey': 'chatMessage/cid',
        'gsiA1SortKey': created_at.to_iso8601_string(),
        'messageId': 'mid',
        'chatId': 'cid',
        'userId': 'uid',
        'createdAt': created_at.to_iso8601_string(),
        'text': text,
        'textTags': text_tags,
    }

    # verify we can't add another chat with same id
    with pytest.raises(chat_message_dynamo.client.exceptions.ConditionalCheckFailedException):
        chat_message_dynamo.client.transact_write_items([transact])


def test_generate_chat_messages_by_chat(chat_message_dynamo):
    chat_id = 'cid'

    # verify with no chat messages / chat doesn't exist
    assert list(chat_message_dynamo.generate_chat_messages_by_chat(chat_id)) == []

    # add a chat message
    message_id_1 = 'mid1'
    transact = chat_message_dynamo.transact_add_chat_message(message_id_1, chat_id, 'uid', 'lore', [])
    chat_message_dynamo.client.transact_write_items([transact])

    # verify with one chat message
    items = list(chat_message_dynamo.generate_chat_messages_by_chat(chat_id))
    assert len(items) == 1
    assert items[0]['messageId'] == message_id_1

    # add another chat message
    message_id_2 = 'mid2'
    transact = chat_message_dynamo.transact_add_chat_message(message_id_2, chat_id, 'uid', 'ipsum', [])
    chat_message_dynamo.client.transact_write_items([transact])

    # verify with two chat messages
    items = list(chat_message_dynamo.generate_chat_messages_by_chat(chat_id))
    assert len(items) == 2
    assert items[0]['messageId'] == message_id_1
    assert items[1]['messageId'] == message_id_2
