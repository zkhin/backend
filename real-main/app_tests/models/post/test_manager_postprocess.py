import logging
from uuid import uuid4

import pendulum
import pytest

from app.models.card.specs import CommentCardSpec
from app.models.post.enums import PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user, str(uuid4()), PostType.TEXT_ONLY, text='go go')


def test_postprocess_comment_added(post_manager, post, user, user2, card_manager):
    card_spec = CommentCardSpec(user.id, post.id)

    # verify starting state
    post.refresh_item()
    assert 'commentCount' not in post.item
    assert 'commentsUnviewedCount' not in post.item
    assert 'gsiA3PartitionKey' not in post.item
    assert 'gsiA3SortKey' not in post.item
    assert card_manager.get_card(card_spec.card_id) is None

    # postprocess a comment by the owner, which is already viewed
    post_manager.postprocess_comment_added(post.id, user.id, 'unused')
    post.refresh_item()
    assert post.item['commentCount'] == 1
    assert 'commentsUnviewedCount' not in post.item
    assert 'gsiA3PartitionKey' not in post.item
    assert 'gsiA3SortKey' not in post.item
    assert card_manager.get_card(card_spec.card_id) is None

    # postprocess a comment by other, which has not yet been viewed
    now = pendulum.now('utc')
    post_manager.postprocess_comment_added(post.id, user2.id, now)
    post.refresh_item()
    assert post.item['commentCount'] == 2
    assert post.item['commentsUnviewedCount'] == 1
    assert post.item['gsiA3PartitionKey'].split('/') == ['post', user.id]
    assert pendulum.parse(post.item['gsiA3SortKey']) == now
    assert card_manager.get_card(card_spec.card_id)

    # postprocess another comment by other, which has not yet been viewed
    now = pendulum.now('utc')
    post_manager.postprocess_comment_added(post.id, user2.id, now)
    post.refresh_item()
    assert post.item['commentCount'] == 3
    assert post.item['commentsUnviewedCount'] == 2
    assert post.item['gsiA3PartitionKey'].split('/') == ['post', user.id]
    assert pendulum.parse(post.item['gsiA3SortKey']) == now
    assert card_manager.get_card(card_spec.card_id)


def test_postprocess_comment_deleted(post_manager, post, user2, caplog):
    # postprocess an add to increment counts, and verify starting state
    post_manager.postprocess_comment_added(post.id, user2.id, pendulum.now('utc'))
    post.refresh_item()
    assert post.item['commentCount'] == 1
    assert post.item['commentsUnviewedCount'] == 1

    # postprocess a deleted comment, verify counts drop as expected
    post_manager.postprocess_comment_deleted(post.id, user2.id, pendulum.now('utc'))
    post.refresh_item()
    assert post.item['commentCount'] == 0
    assert post.item['commentsUnviewedCount'] == 1

    # postprocess a deleted comment, verify fails softly and final state
    with caplog.at_level(logging.WARNING):
        post_manager.postprocess_comment_deleted(post.id, user2.id, pendulum.now('utc'))
    assert len(caplog.records) == 1
    assert 'Failed to decrement comment count' in caplog.records[0].msg
    assert post.id in caplog.records[0].msg
    post.refresh_item()
    assert post.item['commentCount'] == 0
    assert post.item['commentsUnviewedCount'] == 1
