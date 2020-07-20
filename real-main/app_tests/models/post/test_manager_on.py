import logging
from unittest.mock import call, patch
from uuid import uuid4

import pendulum
import pytest

from app.models.card.specs import CommentCardSpec, PostLikesCardSpec, PostViewsCardSpec
from app.models.like.enums import LikeStatus
from app.models.post.enums import PostStatus, PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user, str(uuid4()), PostType.TEXT_ONLY, text='go go')


@pytest.fixture
def flag_item(post, user2):
    post.flag(user2)
    yield post.flag_dynamo.get(post.id, user2.id)


@pytest.fixture
def like_onymous(post, user, like_manager):
    like_manager.like_post(user, post, LikeStatus.ONYMOUSLY_LIKED)
    yield like_manager.get_like(user.id, post.id)


@pytest.fixture
def like_anonymous(post, user2, like_manager):
    like_manager.like_post(user2, post, LikeStatus.ANONYMOUSLY_LIKED)
    yield like_manager.get_like(user2.id, post.id)


def test_on_flag_add(post_manager, post, user2, flag_item):
    # check starting state
    assert post.refresh_item().item.get('flagCount', 0) == 0

    # postprocess, verify flagCount is incremented & not force achived
    post_manager.on_flag_add(post.id, new_item=flag_item)
    assert post.refresh_item().item.get('flagCount', 0) == 1
    assert post.status != PostStatus.ARCHIVED


def test_on_flag_add_force_archive_by_admin(post_manager, post, user2, caplog, flag_item):
    # check starting state
    assert post.refresh_item().item.get('flagCount', 0) == 0

    # postprocess, verify flagCount is incremented and force archived
    with patch.object(post_manager, 'flag_admin_usernames', ('real', user2.username)):
        with caplog.at_level(logging.WARNING):
            post_manager.on_flag_add(post.id, new_item=flag_item)
    assert len(caplog.records) == 1
    assert 'Force archiving post' in caplog.records[0].msg
    assert post.refresh_item().item.get('flagCount', 0) == 1
    assert post.status == PostStatus.ARCHIVED


def test_on_flag_add_force_archive_by_crowdsourced_criteria(post_manager, post, user2, caplog, flag_item):
    # configure and check starting state
    assert post.refresh_item().item.get('flagCount', 0) == 0
    for _ in range(6):
        post.dynamo.increment_viewed_by_count(post.id)

    # postprocess, verify flagCount is incremented and force archived
    with caplog.at_level(logging.WARNING):
        post_manager.on_flag_add(post.id, new_item=flag_item)
    assert len(caplog.records) == 1
    assert 'Force archiving post' in caplog.records[0].msg
    assert post.refresh_item().item.get('flagCount', 0) == 1
    assert post.status == PostStatus.ARCHIVED


def test_on_like_add(post_manager, post, like_onymous, like_anonymous):
    # check starting state
    post.refresh_item()
    assert post.item.get('onymousLikeCount', 0) == 0
    assert post.item.get('anonymousLikeCount', 0) == 0

    # trigger, check state
    post_manager.on_like_add(post.id, like_onymous.item)
    post.refresh_item()
    assert post.item.get('onymousLikeCount', 0) == 1
    assert post.item.get('anonymousLikeCount', 0) == 0

    # trigger, check state
    post_manager.on_like_add(post.id, like_anonymous.item)
    post.refresh_item()
    assert post.item.get('onymousLikeCount', 0) == 1
    assert post.item.get('anonymousLikeCount', 0) == 1

    # trigger, check state
    post_manager.on_like_add(post.id, like_anonymous.item)
    post.refresh_item()
    assert post.item.get('onymousLikeCount', 0) == 1
    assert post.item.get('anonymousLikeCount', 0) == 2

    # checking junk like status
    with pytest.raises(Exception, match='junkjunk'):
        post_manager.on_like_add(post.id, {**like_onymous.item, 'likeStatus': 'junkjunk'})
    post.refresh_item()
    assert post.item.get('onymousLikeCount', 0) == 1
    assert post.item.get('anonymousLikeCount', 0) == 2


def test_on_like_delete(post_manager, post, like_onymous, like_anonymous, caplog):
    # configure and check starting state
    post_manager.dynamo.increment_onymous_like_count(post.id)
    post_manager.dynamo.increment_anonymous_like_count(post.id)
    post.refresh_item()
    assert post.item.get('onymousLikeCount', 0) == 1
    assert post.item.get('anonymousLikeCount', 0) == 1

    # trigger, check state
    post_manager.on_like_delete(post.id, like_onymous.item)
    post.refresh_item()
    assert post.item.get('onymousLikeCount', 0) == 0
    assert post.item.get('anonymousLikeCount', 0) == 1

    # trigger, check state
    post_manager.on_like_delete(post.id, like_anonymous.item)
    post.refresh_item()
    assert post.item.get('onymousLikeCount', 0) == 0
    assert post.item.get('anonymousLikeCount', 0) == 0

    # trigger, check fails softly
    with caplog.at_level(logging.WARNING):
        post_manager.on_like_delete(post.id, like_onymous.item)
    assert len(caplog.records) == 1
    assert 'Failed to decrement' in caplog.records[0].msg
    assert 'onymousLikeCount' in caplog.records[0].msg
    assert post.id in caplog.records[0].msg
    post.refresh_item()
    assert post.item.get('onymousLikeCount', 0) == 0
    assert post.item.get('anonymousLikeCount', 0) == 0

    # checking junk like status
    with pytest.raises(Exception, match='junkjunk'):
        post_manager.on_like_delete(post.id, {**like_onymous.item, 'likeStatus': 'junkjunk'})
    post.refresh_item()
    assert post.item.get('onymousLikeCount', 0) == 0
    assert post.item.get('anonymousLikeCount', 0) == 0


def test_on_view_add_view_by_post_owner_clears_unviewed_comments(post_manager, post):
    # add some state to clear, verify
    post_manager.dynamo.set_last_unviewed_comment_at(post.item, pendulum.now('utc'))
    post_manager.dynamo.increment_comment_count(post.id, viewed=False)
    post.refresh_item()
    assert 'gsiA3PartitionKey' in post.item
    assert post.item.get('commentsUnviewedCount', 0) == 1

    # react to a view by a non-post owner, verify doesn't change state
    post_manager.on_view_add(post.id, {'sortKey': f'view/{uuid4()}'})
    post.refresh_item()
    assert 'gsiA3PartitionKey' in post.item
    assert post.item.get('commentsUnviewedCount', 0) == 1

    # react to a view by post owner, verify state reset
    post_manager.on_view_add(post.id, {'sortKey': f'view/{post.user_id}'})
    post.refresh_item()
    assert 'gsiA3PartitionKey' not in post.item
    assert post.item.get('commentsUnviewedCount', 0) == 0


def test_on_view_add_view_by_post_owner_clears_cards(post_manager, post):
    # react to a view by a non-post owner, verify no calls
    with patch.object(post_manager, 'card_manager') as card_manager_mock:
        post_manager.on_view_add(post.id, {'sortKey': f'view/{uuid4()}'})
    assert len(card_manager_mock.mock_calls) == 0

    # react to a view by post owner, verify calls
    with patch.object(post_manager, 'card_manager') as card_manager_mock:
        post_manager.on_view_add(post.id, {'sortKey': f'view/{post.user_id}'})
    assert len(card_manager_mock.mock_calls) == 3
    card_spec0 = card_manager_mock.mock_calls[0].args[0]
    card_spec1 = card_manager_mock.mock_calls[1].args[0]
    card_spec2 = card_manager_mock.mock_calls[2].args[0]
    assert card_spec0.card_id == CommentCardSpec(post.user_id, post.id).card_id
    assert card_spec1.card_id == PostLikesCardSpec(post.user_id, post.id).card_id
    assert card_spec2.card_id == PostViewsCardSpec(post.user_id, post.id).card_id
    assert card_manager_mock.mock_calls == [
        call.remove_card_by_spec_if_exists(card_spec0),
        call.remove_card_by_spec_if_exists(card_spec1),
        call.remove_card_by_spec_if_exists(card_spec2),
    ]


def test_on_view_add_view_by_post_owner_race_condition(post_manager, post):
    # delete the post from the DB, verify it's gone
    post.delete()
    assert post_manager.get_post(post.id) is None

    # react to a view by post owner, with the manager mocked so the handler
    # thinks the post exists in the DB up until when the writes fail
    with patch.object(post_manager, 'get_post', return_value=post):
        with patch.object(post_manager, 'card_manager') as card_manager_mock:
            post_manager.on_view_add(post.id, {'sortKey': f'view/{post.user_id}'})
    # verify control flowed through to the card_manager calls
    assert len(card_manager_mock.mock_calls) == 3


def test_on_delete_removes_cards(post_manager, post):
    with patch.object(post_manager, 'card_manager') as card_manager_mock:
        post_manager.on_delete(post.id, post.item)
    assert len(card_manager_mock.mock_calls) == 3
    card_spec0 = card_manager_mock.mock_calls[0].args[0]
    card_spec1 = card_manager_mock.mock_calls[1].args[0]
    card_spec2 = card_manager_mock.mock_calls[2].args[0]
    assert card_spec0.card_id == CommentCardSpec(post.user_id, post.id).card_id
    assert card_spec1.card_id == PostLikesCardSpec(post.user_id, post.id).card_id
    assert card_spec2.card_id == PostViewsCardSpec(post.user_id, post.id).card_id
    assert card_manager_mock.mock_calls == [
        call.remove_card_by_spec_if_exists(card_spec0),
        call.remove_card_by_spec_if_exists(card_spec1),
        call.remove_card_by_spec_if_exists(card_spec2),
    ]


def test_on_comment_add(post_manager, post, user, user2, comment_manager):
    # verify starting state
    post.refresh_item()
    assert 'commentCount' not in post.item
    assert 'commentsUnviewedCount' not in post.item
    assert 'gsiA3PartitionKey' not in post.item
    assert 'gsiA3SortKey' not in post.item

    # postprocess a comment by the owner, which is already viewed
    comment = comment_manager.add_comment(str(uuid4()), post.id, user.id, 'lore')
    post_manager.on_comment_add(comment.id, comment.item)
    post.refresh_item()
    assert post.item['commentCount'] == 1
    assert 'commentsUnviewedCount' not in post.item
    assert 'gsiA3PartitionKey' not in post.item
    assert 'gsiA3SortKey' not in post.item

    # postprocess a comment by other, which has not yet been viewed
    now = pendulum.now('utc')
    comment = comment_manager.add_comment(str(uuid4()), post.id, user2.id, 'lore', now=now)
    post_manager.on_comment_add(comment.id, comment.item)
    post.refresh_item()
    assert post.item['commentCount'] == 2
    assert post.item['commentsUnviewedCount'] == 1
    assert post.item['gsiA3PartitionKey'].split('/') == ['post', user.id]
    assert pendulum.parse(post.item['gsiA3SortKey']) == now

    # postprocess another comment by other, which has not yet been viewed
    now = pendulum.now('utc')
    comment = comment_manager.add_comment(str(uuid4()), post.id, user2.id, 'lore', now=now)
    post_manager.on_comment_add(comment.id, comment.item)
    post.refresh_item()
    assert post.item['commentCount'] == 3
    assert post.item['commentsUnviewedCount'] == 2
    assert post.item['gsiA3PartitionKey'].split('/') == ['post', user.id]
    assert pendulum.parse(post.item['gsiA3SortKey']) == now


def test_on_comment_delete(post_manager, post, user2, caplog, comment_manager):
    # configure starting state, verify
    post_manager.dynamo.increment_comment_count(post.id, viewed=False)
    post_manager.dynamo.increment_comment_count(post.id, viewed=False)
    post.refresh_item()
    assert post.item['commentCount'] == 2
    assert post.item['commentsUnviewedCount'] == 2

    # postprocess a deleted comment, verify counts drop as expected
    comment = comment_manager.add_comment(str(uuid4()), post.id, user2.id, 'lore')
    post_manager.on_comment_delete(comment.id, comment.item)
    post.refresh_item()
    assert post.item['commentCount'] == 1
    assert post.item['commentsUnviewedCount'] == 1

    # postprocess a deleted comment, verify counts drop as expected
    post_manager.on_comment_delete(comment.id, comment.item)
    post.refresh_item()
    assert post.item['commentCount'] == 0
    assert post.item['commentsUnviewedCount'] == 0

    # postprocess a deleted comment, verify fails softly and final state
    with caplog.at_level(logging.WARNING):
        post_manager.on_comment_delete(comment.id, comment.item)
    assert len(caplog.records) == 2
    assert 'Failed to decrement commentCount' in caplog.records[0].msg
    assert 'Failed to decrement commentsUnviewedCount' in caplog.records[1].msg
    assert post.id in caplog.records[0].msg
    assert post.id in caplog.records[1].msg
    post.refresh_item()
    assert post.item['commentCount'] == 0
    assert post.item['commentsUnviewedCount'] == 0


def test_comment_deleted_with_post_views(post_manager, post, user, user2, caplog, comment_manager):
    # post owner adds a acomment
    comment1 = comment_manager.add_comment(str(uuid4()), post.id, user.id, 'lore ipsum')
    post_manager.on_comment_add(comment1.id, comment1.item)

    # other user adds a comment
    comment2 = comment_manager.add_comment(str(uuid4()), post.id, user2.id, 'lore ipsum')
    post_manager.on_comment_add(comment2.id, comment2.item)

    # post owner views all the comments
    post_manager.record_views([post.id], user.id)
    post_manager.on_view_add(post.id, {'sortKey': f'view/{user.id}'})

    # other user adds another comment
    comment3 = comment_manager.add_comment(str(uuid4()), post.id, user2.id, 'lore ipsum')
    post_manager.on_comment_add(comment3.id, comment3.item)

    # other user adds another comment
    comment4 = comment_manager.add_comment(str(uuid4()), post.id, user2.id, 'lore ipsum')
    post_manager.on_comment_add(comment4.id, comment4.item)

    # verify starting state
    post.refresh_item()
    assert post.item['commentCount'] == 4
    assert post.item['commentsUnviewedCount'] == 2
    assert pendulum.parse(post.item['gsiA3SortKey']) == comment4.created_at

    # postprocess deleteing comment4, verify state
    post_manager.on_comment_delete(comment4.id, comment4.item)
    post.refresh_item()
    assert post.item['commentCount'] == 3
    assert post.item['commentsUnviewedCount'] == 1
    assert pendulum.parse(post.item['gsiA3SortKey']) == comment4.created_at

    # postprocess deleteing comment2, verify state
    post_manager.on_comment_delete(comment2.id, comment2.item)
    post.refresh_item()
    assert post.item['commentCount'] == 2
    assert post.item['commentsUnviewedCount'] == 1
    assert pendulum.parse(post.item['gsiA3SortKey']) == comment4.created_at

    # postprocess deleteing comment4, verify state
    post_manager.on_comment_delete(comment4.id, comment4.item)
    post.refresh_item()
    assert post.item['commentCount'] == 1
    assert post.item['commentsUnviewedCount'] == 0
    assert 'gsiA3SortKey' not in post.item

    # postprocess deleteing comment1, verify state
    post_manager.on_comment_delete(comment1.id, comment1.item)
    post.refresh_item()
    assert post.item['commentCount'] == 0
    assert post.item['commentsUnviewedCount'] == 0
    assert 'gsiA3SortKey' not in post.item
