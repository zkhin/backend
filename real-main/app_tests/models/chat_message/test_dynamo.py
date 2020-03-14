import pendulum
import pytest

from app.models.chat_message.dynamo import ChatMessageDynamo
from app.models.chat_message.exceptions import ChatMessageException


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


@pytest.mark.xfail(strict=True, reason='https://github.com/spulec/moto/issues/2424')
def test_add_chat_message_view_failures(chat_message_dynamo):
    message_id = 'mid'
    user_id = 'uid'
    viewed_at = pendulum.now('utc')

    # verify can't add view if message doesn't exist
    with pytest.raises(ChatMessageException, match='does not exist'):
        chat_message_dynamo.add_chat_message_view(message_id, user_id, viewed_at)

    # add the chat message
    chat_id = 'cid'
    text = 'lore ipsum'
    text_tags = []
    transact = chat_message_dynamo.transact_add_chat_message(message_id, chat_id, user_id, text, text_tags)
    chat_message_dynamo.client.transact_write_items([transact])

    # verify can't add a view as author of the message
    with pytest.raises(ChatMessageException, match='viewer is author'):
        chat_message_dynamo.add_chat_message_view(message_id, user_id, viewed_at)

    # add a view as another user
    other_user_id = 'ouid'
    chat_message_dynamo.add_chat_message_view(message_id, other_user_id, viewed_at)

    # verify that view has right form in db
    item = chat_message_dynamo.get_chat_view_message(message_id, other_user_id)
    assert item == {
        'partitionKey': 'chatMessageView/mid/ouid',
        'sortKey': '-',
        'schemaVersion': 0,
        'gsiK1PartitionKey': 'chatMessageView/mid',
        'gsiK1SortKey': viewed_at.to_iso8601_string(),
        'messageId': 'mid',
        'userId': 'uid',
        'viewedAt': viewed_at.to_iso8601_string(),
    }

    # can't view the same message twice
    with pytest.raises(ChatMessageException, match='view already exists'):
        chat_message_dynamo.add_chat_message_view(message_id, other_user_id, viewed_at)


def test_add_chat_message_view(chat_message_dynamo):
    # add the chat message
    chat_id = 'cid'
    message_id = 'mid'
    user_id = 'uid'
    text = 'lore ipsum'
    text_tags = []
    transact = chat_message_dynamo.transact_add_chat_message(message_id, chat_id, user_id, text, text_tags)
    chat_message_dynamo.client.transact_write_items([transact])

    # add a view as another user
    other_user_id = 'ouid'
    viewed_at = pendulum.now('utc')
    chat_message_dynamo.add_chat_message_view(message_id, other_user_id, viewed_at)

    # verify that view has right form in db
    item = chat_message_dynamo.get_chat_view_message(message_id, other_user_id)
    assert item == {
        'partitionKey': 'chatMessageView/mid/ouid',
        'sortKey': '-',
        'schemaVersion': 0,
        'gsiK1PartitionKey': 'chatMessageView/mid',
        'gsiK1SortKey': viewed_at.to_iso8601_string(),
        'messageId': 'mid',
        'userId': 'ouid',
        'viewedAt': viewed_at.to_iso8601_string(),
    }


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


def test_generate_chat_message_viewed_by_user_ids_by_message(chat_message_dynamo):
    message_id = 'mid'

    # test generate for message that doesn't exist
    user_ids = list(chat_message_dynamo.generate_chat_message_viewed_by_user_ids_by_message(message_id))
    assert user_ids == []

    # add the chat message
    chat_id = 'cid'
    user_id = 'uid'
    text = 'lore ipsum'
    text_tags = []
    transact = chat_message_dynamo.transact_add_chat_message(message_id, chat_id, user_id, text, text_tags)
    chat_message_dynamo.client.transact_write_items([transact])

    # test generate views message that exists with no views
    user_ids = list(chat_message_dynamo.generate_chat_message_viewed_by_user_ids_by_message(message_id))
    assert user_ids == []

    # add a chat view
    other_user_id_1 = 'ouid1'
    viewed_at = pendulum.now('utc')
    chat_message_dynamo.add_chat_message_view(message_id, other_user_id_1, viewed_at)

    # test we generate that user in our message views
    user_ids = list(chat_message_dynamo.generate_chat_message_viewed_by_user_ids_by_message(message_id))
    assert user_ids == [other_user_id_1]

    # add another chat view
    other_user_id_2 = 'ouid2'
    viewed_at = pendulum.now('utc')
    chat_message_dynamo.add_chat_message_view(message_id, other_user_id_2, viewed_at)

    # test we generate both users in our message views
    user_ids = list(chat_message_dynamo.generate_chat_message_viewed_by_user_ids_by_message(message_id))
    assert user_ids == [other_user_id_1, other_user_id_2]
