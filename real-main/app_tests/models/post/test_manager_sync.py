from unittest.mock import call, patch
from uuid import uuid4

import pytest

from app.models.card.specs import CommentCardSpec, PostLikesCardSpec, PostViewsCardSpec
from app.models.post.enums import PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user, str(uuid4()), PostType.TEXT_ONLY, text='t')


def test_sync_comments_card(post_manager, post):
    # check starting state
    assert 'commentsUnviewedCount' not in post.item

    # add an unviewed comment, check calls
    old_item = post.item.copy()
    post.item['commentsUnviewedCount'] = 1
    with patch.object(post_manager, 'card_manager') as card_manager_mock:
        post_manager.sync_comments_card(post.id, post.item, old_item)
    assert len(card_manager_mock.mock_calls) == 1
    card_spec1 = card_manager_mock.mock_calls[0].args[0]
    assert card_spec1.card_id == CommentCardSpec(post.user_id, post.id).card_id
    assert card_manager_mock.mock_calls == [call.add_or_update_card_by_spec(card_spec1)]

    # add another unviewed comment, check calls
    old_item = post.item.copy()
    post.item['commentsUnviewedCount'] = 2
    with patch.object(post_manager, 'card_manager') as card_manager_mock:
        post_manager.sync_comments_card(post.id, post.item, old_item)
    assert len(card_manager_mock.mock_calls) == 1
    card_spec1 = card_manager_mock.mock_calls[0].args[0]
    assert card_spec1.card_id == CommentCardSpec(post.user_id, post.id).card_id
    assert card_manager_mock.mock_calls == [call.add_or_update_card_by_spec(card_spec1)]

    # jump down to no unviewed comments, check calls
    old_item = post.item.copy()
    post.item['commentsUnviewedCount'] = 0
    with patch.object(post_manager, 'card_manager') as card_manager_mock:
        post_manager.sync_comments_card(post.id, post.item, old_item)
    assert len(card_manager_mock.mock_calls) == 1
    card_spec1 = card_manager_mock.mock_calls[0].args[0]
    assert card_spec1.card_id == CommentCardSpec(post.user_id, post.id).card_id
    assert card_manager_mock.mock_calls == [call.remove_card_by_spec_if_exists(card_spec1)]


def test_sync_post_likes_card(post_manager, post):
    # check starting state
    assert 'onymousLikeCount' not in post.item
    assert 'anonymousLikeCount' not in post.item

    # record a like, verify calls
    old_item = post.item.copy()
    post.item['anonymousLikeCount'] = 1
    with patch.object(post_manager, 'card_manager') as card_manager_mock:
        post_manager.sync_post_likes_card(post.id, post.item, old_item)
    assert len(card_manager_mock.mock_calls) == 1
    card_spec1 = card_manager_mock.mock_calls[0].args[0]
    assert card_spec1.card_id == PostLikesCardSpec(post.user_id, post.id).card_id
    assert card_manager_mock.mock_calls == [call.add_or_update_card_by_spec(card_spec1)]

    # record a up to nine likes, verify calls
    old_item = post.item.copy()
    post.item['onymousLikeCount'] = 8
    with patch.object(post_manager, 'card_manager') as card_manager_mock:
        post_manager.sync_post_likes_card(post.id, post.item, old_item)
    assert len(card_manager_mock.mock_calls) == 1
    card_spec1 = card_manager_mock.mock_calls[0].args[0]
    assert card_spec1.card_id == PostLikesCardSpec(post.user_id, post.id).card_id
    assert card_manager_mock.mock_calls == [call.add_or_update_card_by_spec(card_spec1)]

    # record a up to 10th like, verify no call
    old_item = post.item.copy()
    post.item['anonymousLikeCount'] = 2
    with patch.object(post_manager, 'card_manager') as card_manager_mock:
        post_manager.sync_post_likes_card(post.id, post.item, old_item)
    assert card_manager_mock.mock_calls == []


def test_sync_post_views_card(post_manager, post):
    # check starting state
    assert 'viewedByCount' not in post.item

    # jump up to five views, process, check no calls
    old_item = post.item.copy()
    post.item['viewedByCount'] = 5
    with patch.object(post_manager, 'card_manager') as card_manager_mock:
        post_manager.sync_post_views_card(post.id, post.item, old_item)
    assert card_manager_mock.mock_calls == []

    # go to six views, process, check call happens
    old_item = post.item.copy()
    post.item['viewedByCount'] = 6
    with patch.object(post_manager, 'card_manager') as card_manager_mock:
        post_manager.sync_post_views_card(post.id, post.item, old_item)
    assert len(card_manager_mock.mock_calls) == 1
    card_spec1 = card_manager_mock.mock_calls[0].args[0]
    assert card_spec1.card_id == PostViewsCardSpec(post.user_id, post.id).card_id
    assert card_manager_mock.mock_calls == [call.add_or_update_card_by_spec(card_spec1)]

    # jump up to seven views, process, check no calls
    old_item = post.item.copy()
    post.item['viewedByCount'] = 7
    with patch.object(post_manager, 'card_manager') as card_manager_mock:
        post_manager.sync_post_views_card(post.id, post.item, old_item)
    assert card_manager_mock.mock_calls == []
