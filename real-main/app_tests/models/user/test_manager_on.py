import logging
from unittest.mock import call, patch
from uuid import uuid4

import pytest

from app.models.post.enums import PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def comment(user, post_manager, comment_manager):
    post = post_manager.add_post(user, str(uuid4()), PostType.TEXT_ONLY, text='go go')
    yield comment_manager.add_comment(str(uuid4()), post.id, user.id, 'run far')


@pytest.fixture
def card(user, card_manager):
    yield card_manager.add_card(user.id, 'card title', 'https://action')


@pytest.fixture
def chat(user, chat_manager):
    yield chat_manager.add_group_chat(str(uuid4()), user)


def test_on_comment_add_adjusts_counts(user_manager, user, comment):
    # check & save starting state
    org_item = user.refresh_item().item
    assert 'commentCount' not in org_item

    # process, check state
    user_manager.on_comment_add(comment.id, comment.item)
    assert user.refresh_item().item['commentCount'] == 1

    # process, check state
    user_manager.on_comment_add(comment.id, comment.item)
    assert user.refresh_item().item['commentCount'] == 2

    # check for unexpected state changes
    new_item = user.item
    new_item.pop('commentCount')
    assert new_item == org_item


def test_on_comment_delete_adjusts_counts(user_manager, user, comment, caplog):
    # configure, check & save starting state
    user_manager.on_comment_add(comment.id, comment.item)
    org_item = user.refresh_item().item
    assert org_item['commentCount'] == 1
    assert 'commentDeletedCount' not in org_item

    # process, check state
    user_manager.on_comment_delete(comment.id, comment.item)
    new_item = user.refresh_item().item
    assert new_item['commentCount'] == 0
    assert new_item['commentDeletedCount'] == 1

    # process again, verify fails softly
    with caplog.at_level(logging.WARNING):
        user_manager.on_comment_delete(comment.id, comment.item)
    assert len(caplog.records) == 1
    assert 'Failed to decrement' in caplog.records[0].msg
    assert 'commentCount' in caplog.records[0].msg
    assert user.id in caplog.records[0].msg
    new_item = user.refresh_item().item
    assert new_item['commentCount'] == 0
    assert new_item['commentDeletedCount'] == 2

    # check for unexpected state changes
    del new_item['commentCount'], org_item['commentCount'], new_item['commentDeletedCount']
    assert new_item == org_item


def test_on_user_delete_calls_elasticsearch(user_manager, user):
    with patch.object(user_manager, 'elasticsearch_client') as elasticsearch_client_mock:
        user_manager.on_user_delete(user.id, user.item)
    assert elasticsearch_client_mock.mock_calls == [call.delete_user(user.id)]


def test_on_user_delete_calls_pinpoint(user_manager, user):
    with patch.object(user_manager, 'pinpoint_client') as pinpoint_client_mock:
        user_manager.on_user_delete(user.id, user.item)
    assert pinpoint_client_mock.mock_calls == [call.delete_user_endpoints(user.id)]


def test_on_card_add_increments_card_count(user_manager, user, card):
    assert user.refresh_item().item.get('cardCount', 0) == 0

    # handle add, verify state
    user_manager.on_card_add(card.id, card.item)
    assert user.refresh_item().item.get('cardCount', 0) == 1

    # handle add, verify state
    user_manager.on_card_add(card.id, card.item)
    assert user.refresh_item().item.get('cardCount', 0) == 2


def test_on_card_delete_decrements_card_count(user_manager, user, card, caplog):
    user_manager.dynamo.increment_card_count(user.id)
    assert user.refresh_item().item.get('cardCount', 0) == 1

    # handle delete, verify state
    user_manager.on_card_delete(card.id, card.item)
    assert user.refresh_item().item.get('cardCount', 0) == 0

    # handle delete, verify fails softly and state unchanged
    with caplog.at_level(logging.WARNING):
        user_manager.on_card_delete(card.id, card.item)
    assert len(caplog.records) == 1
    assert 'Failed to decrement' in caplog.records[0].msg
    assert 'cardCount' in caplog.records[0].msg
    assert user.id in caplog.records[0].msg
    assert user.refresh_item().item.get('cardCount', 0) == 0


def test_on_chat_member_add_update_chat_count(user_manager, chat, user):
    # check starting state
    member_item = chat.member_dynamo.get(chat.id, user.id)
    assert member_item
    assert user.refresh_item().item.get('chatCount', 0) == 0

    # react to an add, check state
    user_manager.on_chat_member_add_update_chat_count(chat.id, new_item=member_item)
    assert user.refresh_item().item.get('chatCount', 0) == 1

    # react to another add, check state
    user_manager.on_chat_member_add_update_chat_count(chat.id, new_item=member_item)
    assert user.refresh_item().item.get('chatCount', 0) == 2


def test_on_chat_member_delete_update_chat_count(user_manager, chat, user, caplog):
    # configure and check starting state
    member_item = chat.member_dynamo.get(chat.id, user.id)
    assert member_item
    user_manager.dynamo.increment_chat_count(user.id)
    assert user.refresh_item().item.get('chatCount', 0) == 1

    # react to an delete, check state
    user_manager.on_chat_member_delete_update_chat_count(chat.id, old_item=member_item)
    assert user.refresh_item().item.get('chatCount', 0) == 0

    # react to another delete, verify fails softly
    with caplog.at_level(logging.WARNING):
        user_manager.on_chat_member_delete_update_chat_count(chat.id, old_item=member_item)
    assert len(caplog.records) == 1
    assert 'Failed to decrement' in caplog.records[0].msg
    assert 'chatCount' in caplog.records[0].msg
    assert user.id in caplog.records[0].msg
    assert user.refresh_item().item.get('chatCount', 0) == 0
