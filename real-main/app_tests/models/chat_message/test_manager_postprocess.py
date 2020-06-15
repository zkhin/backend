from uuid import uuid4

import pendulum
import pytest

from app.mixins.view.enums import ViewedStatus
from app.models.card.specs import ChatCardSpec


@pytest.fixture
def user1(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user1


@pytest.fixture
def chat(chat_manager, user1, user2):
    yield chat_manager.add_direct_chat('cid', user1.id, user2.id)


@pytest.fixture
def message1(chat_message_manager, chat, user1):
    yield chat_message_manager.add_chat_message(str(uuid4()), 'lore ipsum', chat.id, user1.id)


@pytest.fixture
def message2(chat_message_manager, chat, user2):
    yield chat_message_manager.add_chat_message(str(uuid4()), 'lore ipsum', chat.id, user2.id)


@pytest.fixture
def message3(chat_message_manager, chat, user2):
    yield chat_message_manager.add_chat_message(str(uuid4()), 'lore ipsum', chat.id, user2.id)


def test_postprocess_chat_message_added(
    chat_message_manager, card_manager, chat, message1, message2, message3, user1, user2
):
    chat_message_dynamo = chat_message_manager.dynamo
    member_dynamo = chat.member_dynamo
    pk1, sk1 = message1.item['partitionKey'], message1.item['sortKey']
    pk2, sk2 = message2.item['partitionKey'], message2.item['sortKey']
    pk3, sk3 = message3.item['partitionKey'], message3.item['sortKey']
    old_item = None
    new_item1 = chat_message_dynamo.client.get_typed_item(chat_message_dynamo.typed_pk(message1.id))
    new_item2 = chat_message_dynamo.client.get_typed_item(chat_message_dynamo.typed_pk(message2.id))
    new_item3 = chat_message_dynamo.client.get_typed_item(chat_message_dynamo.typed_pk(message3.id))
    assert message1.item['createdAt'] < message2.item['createdAt'] < message3.item['createdAt']
    spec1 = ChatCardSpec(user1.id)
    spec2 = ChatCardSpec(user2.id)

    # verify starting state
    chat.refresh_item()
    assert 'messageCount' not in chat.item
    assert 'lastMessageActivityAt' not in chat.item
    assert member_dynamo.get(chat.id, user1.id)['gsiK2SortKey'].split('/') == ['chat', chat.item['createdAt']]
    assert member_dynamo.get(chat.id, user2.id)['gsiK2SortKey'].split('/') == ['chat', chat.item['createdAt']]
    assert card_manager.get_card(spec1.card_id) is None
    assert card_manager.get_card(spec2.card_id) is None

    # process the first new chat message, verify
    chat_message_manager.postprocess_record(pk1, sk1, old_item, new_item1)
    chat.refresh_item()
    assert chat.item['messageCount'] == 1
    assert chat.item['lastMessageActivityAt'] == message1.item['createdAt']
    assert member_dynamo.get(chat.id, user1.id)['gsiK2SortKey'].split('/') == ['chat', message1.item['createdAt']]
    assert member_dynamo.get(chat.id, user2.id)['gsiK2SortKey'].split('/') == ['chat', message1.item['createdAt']]
    assert card_manager.get_card(spec1.card_id) is None
    assert card_manager.get_card(spec2.card_id)

    # process the third new chat message, verify
    chat_message_manager.postprocess_record(pk2, sk2, old_item, new_item3)
    chat.refresh_item()
    assert chat.item['messageCount'] == 2
    assert chat.item['lastMessageActivityAt'] == message3.item['createdAt']
    assert member_dynamo.get(chat.id, user1.id)['gsiK2SortKey'].split('/') == ['chat', message3.item['createdAt']]
    assert member_dynamo.get(chat.id, user2.id)['gsiK2SortKey'].split('/') == ['chat', message3.item['createdAt']]
    assert card_manager.get_card(spec1.card_id)
    assert card_manager.get_card(spec2.card_id)

    # process the second new chat message out of order, verify handled correctly
    chat_message_manager.postprocess_record(pk3, sk3, old_item, new_item2)
    chat.refresh_item()
    assert chat.item['messageCount'] == 3
    assert chat.item['lastMessageActivityAt'] == message3.item['createdAt']
    assert member_dynamo.get(chat.id, user1.id)['gsiK2SortKey'].split('/') == ['chat', message3.item['createdAt']]
    assert member_dynamo.get(chat.id, user2.id)['gsiK2SortKey'].split('/') == ['chat', message3.item['createdAt']]
    assert card_manager.get_card(spec1.card_id)
    assert card_manager.get_card(spec2.card_id)


def test_postprocess_chat_message_edited(chat_message_manager, card_manager, chat, message1, user1, user2):
    chat_message_dynamo = chat_message_manager.dynamo
    member_dynamo = chat.member_dynamo
    spec1 = ChatCardSpec(user1.id)
    spec2 = ChatCardSpec(user2.id)
    pk, sk = message1.item['partitionKey'], message1.item['sortKey']

    # first do an 'add' of that message, check state
    old_item = None
    new_item = chat_message_dynamo.client.get_typed_item(chat_message_dynamo.typed_pk(message1.id))
    chat_message_manager.postprocess_record(pk, sk, old_item, new_item)
    chat.refresh_item()
    assert chat.item['messageCount'] == 1
    assert chat.item['lastMessageActivityAt'] == message1.item['createdAt']
    assert member_dynamo.get(chat.id, user1.id)['gsiK2SortKey'].split('/') == ['chat', message1.item['createdAt']]
    assert member_dynamo.get(chat.id, user2.id)['gsiK2SortKey'].split('/') == ['chat', message1.item['createdAt']]

    # reset card state, verify
    card_manager.get_card(spec2.card_id).delete()
    assert card_manager.get_card(spec1.card_id) is None
    assert card_manager.get_card(spec2.card_id) is None

    # get images corresponding to an edit
    pk, sk = message1.item['partitionKey'], message1.item['sortKey']
    old_item = chat_message_dynamo.client.get_typed_item(chat_message_dynamo.typed_pk(message1.id))
    message1.edit('the new lore ipsum')
    new_item = chat_message_dynamo.client.get_typed_item(chat_message_dynamo.typed_pk(message1.id))
    assert 'lastEditedAt' not in old_item
    assert new_item['lastEditedAt']['S'] == message1.item['lastEditedAt']
    assert old_item['createdAt']['S'] == new_item['createdAt']['S']
    assert new_item['lastEditedAt']['S'] > old_item['createdAt']['S']

    # process the 'message edited', verify final state
    chat_message_manager.postprocess_record(pk, sk, old_item, new_item)
    chat.refresh_item()
    assert chat.item['messageCount'] == 1
    assert chat.item['lastMessageActivityAt'] == message1.item['lastEditedAt']
    assert member_dynamo.get(chat.id, user1.id)['gsiK2SortKey'].split('/') == ['chat', message1.item['lastEditedAt']]
    assert member_dynamo.get(chat.id, user2.id)['gsiK2SortKey'].split('/') == ['chat', message1.item['lastEditedAt']]
    assert card_manager.get_card(spec1.card_id) is None
    assert card_manager.get_card(spec2.card_id)


def test_postprocess_chat_message_deleted(chat_message_manager, card_manager, chat, message1, user1, user2):
    chat_message_dynamo = chat_message_manager.dynamo
    member_dynamo = chat.member_dynamo
    spec1 = ChatCardSpec(user1.id)
    spec2 = ChatCardSpec(user2.id)
    pk, sk = message1.item['partitionKey'], message1.item['sortKey']

    # first do an 'add' of that message, check state
    old_item = None
    new_item = chat_message_dynamo.client.get_typed_item(chat_message_dynamo.typed_pk(message1.id))
    chat_message_manager.postprocess_record(pk, sk, old_item, new_item)
    chat.refresh_item()
    assert chat.item['messageCount'] == 1
    assert chat.item['lastMessageActivityAt'] == message1.item['createdAt']
    assert member_dynamo.get(chat.id, user1.id)['gsiK2SortKey'].split('/') == ['chat', message1.item['createdAt']]
    assert member_dynamo.get(chat.id, user2.id)['gsiK2SortKey'].split('/') == ['chat', message1.item['createdAt']]

    # reset card state, verify
    card_manager.get_card(spec2.card_id).delete()
    assert card_manager.get_card(spec1.card_id) is None
    assert card_manager.get_card(spec2.card_id) is None

    # process the 'message deleted', verify final state
    old_item = new_item
    new_item = None
    chat_message_manager.postprocess_record(pk, sk, old_item, new_item)
    chat.refresh_item()
    assert chat.item['messageCount'] == 0
    assert chat.item['lastMessageActivityAt'] == message1.item['createdAt']
    assert member_dynamo.get(chat.id, user1.id)['gsiK2SortKey'].split('/') == ['chat', message1.item['createdAt']]
    assert member_dynamo.get(chat.id, user2.id)['gsiK2SortKey'].split('/') == ['chat', message1.item['createdAt']]
    assert card_manager.get_card(spec1.card_id) is None
    assert card_manager.get_card(spec2.card_id) is None  # no card emited for deletes of messages


def test_postprocess_system_message_added(chat_message_manager, card_manager, chat, user1, user2):
    chat_message_dynamo = chat_message_manager.dynamo
    member_dynamo = chat.member_dynamo
    message = chat_message_manager.add_system_message(chat.id, 'lore ipsum')
    pk, sk = message.item['partitionKey'], message.item['sortKey']
    old_item = None
    new_item = chat_message_dynamo.client.get_typed_item(chat_message_dynamo.typed_pk(message.id))
    spec1 = ChatCardSpec(user1.id)
    spec2 = ChatCardSpec(user2.id)

    # verify starting state
    chat.refresh_item()
    assert 'messageCount' not in chat.item
    assert 'lastMessageActivityAt' not in chat.item
    assert member_dynamo.get(chat.id, user1.id)['gsiK2SortKey'].split('/') == ['chat', chat.item['createdAt']]
    assert member_dynamo.get(chat.id, user2.id)['gsiK2SortKey'].split('/') == ['chat', chat.item['createdAt']]
    assert card_manager.get_card(spec1.card_id) is None
    assert card_manager.get_card(spec2.card_id) is None

    # post-process the message add
    chat_message_manager.postprocess_record(pk, sk, old_item, new_item)
    chat.refresh_item()
    assert chat.item['messageCount'] == 1
    assert chat.item['lastMessageActivityAt'] == message.item['createdAt']
    assert member_dynamo.get(chat.id, user1.id)['gsiK2SortKey'].split('/') == ['chat', message.item['createdAt']]
    assert member_dynamo.get(chat.id, user2.id)['gsiK2SortKey'].split('/') == ['chat', message.item['createdAt']]
    assert card_manager.get_card(spec1.card_id)
    assert card_manager.get_card(spec2.card_id)


def test_postprocess_message_view_add_update_delete(chat_message_manager, chat, message1, user2):
    # verify starting state
    assert message1.get_viewed_status(user2.id) == ViewedStatus.NOT_VIEWED
    assert 'viewedMessageCount' not in chat.member_dynamo.get(chat.id, user2.id)
    view_item = message1.view_dynamo.add_view(message1.id, user2.id, 1, pendulum.now('utc'))
    pk, sk = view_item['partitionKey'], view_item['sortKey']

    # post-process the message view add
    old_item = None
    new_item = message1.view_dynamo.client.get_typed_item(message1.view_dynamo.typed_pk(message1.id, user2.id))
    chat_message_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat.member_dynamo.get(chat.id, user2.id)['viewedMessageCount'] == 1

    # post-process message view edit (nothing should change)
    old_item = new_item
    chat_message_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat.member_dynamo.get(chat.id, user2.id)['viewedMessageCount'] == 1

    # post-process messge view delete
    new_item = None
    chat_message_manager.postprocess_record(pk, sk, old_item, new_item)
    assert chat.member_dynamo.get(chat.id, user2.id)['viewedMessageCount'] == 0

    # verify trying decrement below zero is rejected
    with pytest.raises(chat.dynamo.client.exceptions.ConditionalCheckFailedException):
        chat_message_manager.postprocess_record(pk, sk, old_item, new_item)
