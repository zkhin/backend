import json
import unittest.mock as mock

import pendulum
import pytest

from app.models.block.enums import BlockStatus
from app.models.post.enums import PostType
from app.mixins.view.enums import ViewedStatus


@pytest.fixture
def user1(user_manager, post_manager, grant_data_b64, cognito_client):
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username='pbuid')
    user = user_manager.create_cognito_only_user('pbuid', 'pbUname')
    # give the user a profile photo so that it will show up in the message notification trigger calls
    post = post_manager.add_post(user, 'pid', PostType.IMAGE, image_input={'imageData': grant_data_b64})
    user.update_photo(post.id)
    yield user


@pytest.fixture
def user2(user_manager, cognito_client):
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username='pbuid2')
    yield user_manager.create_cognito_only_user('pbuid2', 'pbUname2')


@pytest.fixture
def user3(user_manager, cognito_client):
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username='pbuid3')
    yield user_manager.create_cognito_only_user('pbuid3', 'pbUname3')


@pytest.fixture
def chat(chat_manager, user1, user2):
    yield chat_manager.add_direct_chat('cid', user1.id, user2.id)


@pytest.fixture
def message(chat_message_manager, chat, user1):
    message_id = 'mid'
    text = 'lore ipsum'
    yield chat_message_manager.add_chat_message(message_id, text, chat.id, user1.id)


def test_chat_message_serialize(message, user1, user2, chat):
    # check that user1 has viewed it (since they wrote it) and user2 has not
    message.serialize(user1.id)['viewedStatus'] == ViewedStatus.VIEWED
    message.serialize(user1.id)['author']['blockerStatus'] == BlockStatus.SELF
    message.serialize(user2.id)['viewedStatus'] == ViewedStatus.NOT_VIEWED
    message.serialize(user2.id)['author']['blockerStatus'] == BlockStatus.NOT_BLOCKING

    # user2 reports to have viewed it, check that reflects in the viewedStatus
    message.record_view_count(user2.id, 1)
    message.serialize(user2.id)['viewedStatus'] == ViewedStatus.VIEWED


def test_chat_message_edit(message, chat, user1, user2, card_manager):
    card_id = f'{user2.id}:{card_manager.enums.CHAT_ACTIVITY_CARD.name}'

    # check starting state
    chat.refresh_item()
    assert chat.item['messageCount'] == 1
    assert chat.item['lastMessageActivityAt'] == message.item['createdAt']
    assert message.item['text'] == 'lore ipsum'
    assert message.item['textTags'] == []
    assert 'lastEditedAt' not in message.item

    # clear starting state card state
    card_manager.get_card(card_id).delete()
    assert card_manager.get_card(card_id) is None

    # check starting chat membership sort order state
    gsi_k2_sort_key = 'chat/' + message.item['createdAt']
    assert chat.member_dynamo.get(chat.id, user1.id)['gsiK2SortKey'] == gsi_k2_sort_key
    assert chat.member_dynamo.get(chat.id, user2.id)['gsiK2SortKey'] == gsi_k2_sort_key

    # edit the message
    username = user1.item['username']
    new_text = f'whats up with @{username}?'
    now = pendulum.now('utc')
    message.edit(new_text, now=now)
    assert message.item['text'] == new_text
    assert message.item['textTags'] == [{'tag': f'@{username}', 'userId': user1.id}]
    assert pendulum.parse(message.item['lastEditedAt']) == now

    # check state in dynamo
    chat.refresh_item()
    assert chat.item['messageCount'] == 1
    assert chat.item['lastMessageActivityAt'] == message.item['lastEditedAt']
    message.refresh_item()
    assert message.item['text'] == new_text
    assert message.item['textTags'] == [{'tag': f'@{username}', 'userId': user1.id}]
    assert pendulum.parse(message.item['lastEditedAt']) == now

    # check the card got created
    assert card_manager.get_card(card_id) is not None

    # check final chat membership sort order state
    membership_1 = chat.member_dynamo.get(chat.id, user1.id)
    membership_2 = chat.member_dynamo.get(chat.id, user2.id)
    assert pendulum.parse(membership_1['gsiK2SortKey'][len('chat/'):]) == now
    assert pendulum.parse(membership_2['gsiK2SortKey'][len('chat/'):]) == now


def test_chat_message_delete(message, chat, user1, user2, card_manager):
    card_id = f'{user2.id}:{card_manager.enums.CHAT_ACTIVITY_CARD.name}'

    # double check starting state
    chat.refresh_item()
    message.refresh_item()
    assert chat.item['messageCount'] == 1
    assert chat.item['lastMessageActivityAt'] == message.item['createdAt']
    assert message.item

    # clear starting state card state
    card_manager.get_card(card_id).delete()
    assert card_manager.get_card(card_id) is None

    # check starting chat membership sort order state
    gsi_k2_sort_key = 'chat/' + message.item['createdAt']
    assert chat.member_dynamo.get(chat.id, user1.id)['gsiK2SortKey'] == gsi_k2_sort_key
    assert chat.member_dynamo.get(chat.id, user2.id)['gsiK2SortKey'] == gsi_k2_sort_key

    # delete the message
    now = pendulum.now('utc')
    message.delete(now=now)
    # we need to be able to serialize the gql response, so keep the in-mem item around
    assert message.item

    # check state in dynamo
    chat.refresh_item()
    assert chat.item['messageCount'] == 0
    assert pendulum.parse(chat.item['lastMessageActivityAt']) == now
    message.refresh_item()
    assert message.item is None

    # check the card got created
    assert card_manager.get_card(card_id) is not None

    # check final chat membership sort order state
    membership_1 = chat.member_dynamo.get(chat.id, user1.id)
    membership_2 = chat.member_dynamo.get(chat.id, user2.id)
    assert pendulum.parse(membership_1['gsiK2SortKey'][len('chat/'):]) == now
    assert pendulum.parse(membership_2['gsiK2SortKey'][len('chat/'):]) == now


def test_get_author_encoded(chat_message_manager, user1, user2, user3, chat, block_manager):
    # regular message
    message = chat_message_manager.add_chat_message('mid', 'lore', chat.id, user1.id)
    author_encoded = message.get_author_encoded(user3.id)
    assert author_encoded
    author_serialized = json.loads(author_encoded)
    assert author_serialized['userId'] == user1.id
    assert author_serialized['username'] == user1.username
    assert author_serialized['photoPostId'] == user1.item['photoPostId']
    assert author_serialized['blockerStatus'] == 'NOT_BLOCKING'
    assert author_serialized['blockedStatus'] == 'NOT_BLOCKING'

    # add a blocking relationship
    block_manager.block(user1, user3)
    assert message.get_author_encoded(user3.id) is None

    # test the blocking relationship in the other direction
    message = chat_message_manager.add_chat_message('mid2', 'lore', chat.id, user3.id)
    assert message.get_author_encoded(user1.id) is None

    # test with no author (simulates a system message)
    message = chat_message_manager.add_chat_message('mid3', 'lore', chat.id, user2.id)
    assert message.get_author_encoded(user1.id)
    message._author = None
    assert message.get_author_encoded(user1.id) is None


def test_trigger_notifications_direct(message, chat, user1, user2, appsync_client):
    message.appsync = mock.Mock()
    message.trigger_notifications('ntype')
    assert message.appsync.mock_calls == [mock.call.trigger_notification('ntype', user2.id, message)]


def test_trigger_notifications_user_ids(message, chat, user1, user2, user3, appsync_client):
    # trigger a notification and check that we can use user_ids param to push
    # the notifications to users that aren't found in dynamo
    message.appsync = mock.Mock()
    message.trigger_notifications('ntype', user_ids=[user2.id, user3.id])
    assert message.appsync.mock_calls == [
        mock.call.trigger_notification('ntype', user2.id, message),
        mock.call.trigger_notification('ntype', user3.id, message),
    ]


def test_trigger_notifications_group(chat_manager, chat_message_manager, user1, user2, user3, appsync_client):
    # user1 creates a group chat with everyone in it
    group_chat = chat_manager.add_group_chat('cid', user1)
    group_chat.add(user1, [user2.id, user3.id])

    # user2 creates a message, trigger notificaitons on it
    message_id = 'mid'
    message = chat_message_manager.add_chat_message(message_id, 'lore', group_chat.id, user2.id)
    message.appsync = mock.Mock()
    message.trigger_notifications('ntype')
    assert message.appsync.mock_calls == [
        mock.call.trigger_notification('ntype', user1.id, message),
        mock.call.trigger_notification('ntype', user3.id, message),
    ]

    # add system message, notifications are triggered automatically
    appsync_client.reset_mock()
    message = chat_message_manager.add_system_message_group_name_edited(group_chat.id, user3, 'cname')
    assert len(appsync_client.send.mock_calls) == 3  # one for each member of the group chat


def test_record_view_count(message, user1, user2):
    assert message.get_viewed_status(user1.id) == ViewedStatus.VIEWED  # author
    assert message.get_viewed_status(user2.id) == ViewedStatus.NOT_VIEWED

    # author can't record views
    assert message.record_view_count(user1.id, 2) is False
    assert message.get_viewed_status(user1.id) == ViewedStatus.VIEWED

    # rando can record views
    assert message.record_view_count(user2.id, 2) is True
    assert message.get_viewed_status(user2.id) == ViewedStatus.VIEWED
