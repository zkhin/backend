import logging
import uuid

import pendulum
import pytest

from app.models.card.specs import CommentCardSpec
from app.models.post.enums import PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user
user3 = user


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user, 'pid', PostType.TEXT_ONLY, text='go go')


def test_add_comment(comment_manager, user, post):
    comment_id = 'cid'

    # check our starting state
    assert user.item.get('commentCount', 0) == 0
    assert comment_manager.get_comment(comment_id) is None

    # add the comment, verify
    username = user.item['username']
    text = f'hey @{username}'
    now = pendulum.now('utc')
    comment = comment_manager.add_comment(comment_id, post.id, user.id, text, now=now)
    assert comment.id == comment_id
    assert comment.item['postId'] == post.id
    assert comment.item['userId'] == user.id
    assert comment.item['text'] == text
    assert comment.item['textTags'] == [{'tag': f'@{username}', 'userId': user.id}]
    assert comment.item['commentedAt'] == now.to_iso8601_string()

    # check the post counter incremented, no new comment acitivy b/c the post owner commented
    post.refresh_item()
    assert post.item.get('hasNewCommentActivity', False) is False
    user.refresh_item()
    assert user.item['commentCount'] == 1
    assert user.item.get('postHasNewCommentActivityCount', 0) == 0


def test_add_comment_cant_reuse_ids(comment_manager, user, post):
    comment_id = 'cid'
    text = 'lore'

    # add a comment, verify
    comment = comment_manager.add_comment(comment_id, post.id, user.id, text)
    assert comment.id == comment_id

    # verify we can't add another
    with pytest.raises(comment_manager.exceptions.CommentException):
        comment_manager.add_comment(comment_id, post.id, user.id, text)


def test_cant_comment_to_post_that_doesnt_exist(comment_manager, user):
    # verify we can't add another
    with pytest.raises(comment_manager.exceptions.CommentException):
        comment_manager.add_comment('cid', 'dne-pid', user.id, 't')


def test_cant_comment_on_post_with_comments_disabled(comment_manager, user, post):
    comment_id = 'cid'

    # disable comments on the post, verify we cannot add a comment
    post.set(comments_disabled=True)
    with pytest.raises(comment_manager.exceptions.CommentException):
        comment_manager.add_comment(comment_id, post.id, user.id, 't')

    # enable comments on the post, verify we now can comment
    post.set(comments_disabled=False)
    comment = comment_manager.add_comment(comment_id, post.id, user.id, 't')
    assert comment.id == comment_id


def test_cant_comment_if_block_exists_with_post_owner(comment_manager, user, post, block_manager, user2):
    comment_id = 'cid'
    commenter = user2

    # owner blocks commenter, verify cannot comment
    block_manager.block(user, commenter)
    with pytest.raises(comment_manager.exceptions.CommentException):
        comment_manager.add_comment(comment_id, post.id, commenter.id, 't')

    # owner unblocks commenter, commenter blocks owner, verify cannot comment
    block_manager.unblock(user, commenter)
    block_manager.block(commenter, user)
    with pytest.raises(comment_manager.exceptions.CommentException):
        comment_manager.add_comment(comment_id, post.id, commenter.id, 't')

    # we commenter unblocks owner, verify now can comment
    block_manager.unblock(commenter, user)
    comment = comment_manager.add_comment(comment_id, post.id, commenter.id, 't')
    assert comment.id == comment_id


def test_non_follower_cant_comment_if_private_post_owner(comment_manager, user, post, follow_manager, user2):
    comment_id = 'cid'
    commenter = user2

    # post owner goes private
    user.set_privacy_status(user.enums.UserPrivacyStatus.PRIVATE)

    # verify we can't comment on their post
    with pytest.raises(comment_manager.exceptions.CommentException):
        comment_manager.add_comment(comment_id, post.id, commenter.id, 't')

    # request to follow, verify can't comment
    follow_manager.request_to_follow(commenter, user)
    with pytest.raises(comment_manager.exceptions.CommentException):
        comment_manager.add_comment(comment_id, post.id, commenter.id, 't')

    # deny the follow request, verify can't comment
    follow_manager.get_follow(commenter.id, user.id).deny()
    with pytest.raises(comment_manager.exceptions.CommentException):
        comment_manager.add_comment(comment_id, post.id, commenter.id, 't')

    # accept the follow request, verify can comment
    follow_manager.get_follow(commenter.id, user.id).accept()
    comment = comment_manager.add_comment(comment_id, post.id, commenter.id, 't')
    assert comment.id == comment_id


def test_private_user_can_comment_on_own_post(comment_manager, user, post):
    comment_id = 'cid'

    # post owner goes private
    user.set_privacy_status(user.enums.UserPrivacyStatus.PRIVATE)

    comment = comment_manager.add_comment(comment_id, post.id, user.id, 't')
    assert comment.id == comment_id


def test_delete_all_by_user(comment_manager, user, post, user2, user3):
    # add a comment by an unrelated user for distraction
    comment_other = comment_manager.add_comment('coid', post.id, user2.id, 'lore')

    # add two comments by our target user
    comment_1 = comment_manager.add_comment('cid1', post.id, user3.id, 'lore')
    comment_2 = comment_manager.add_comment('cid2', post.id, user3.id, 'lore')

    # check post comment count, their comment count
    post.refresh_item().item.get('commentCount', 0) == 3
    user3.refresh_item().item.get('commentCount', 0) == 2

    # delete all the comments by the user, verify it worked
    comment_manager.delete_all_by_user(user3.id)
    assert comment_manager.get_comment(comment_1.id) is None
    assert comment_manager.get_comment(comment_2.id) is None

    # verify the unrelated comment was untouched
    assert comment_manager.get_comment(comment_other.id)

    # check post & user comment count
    post.refresh_item().item.get('commentCount', 0) == 1
    user3.refresh_item().item.get('commentCount', 0) == 0


def test_delete_all_on_post(comment_manager, user, post, post_manager, user2, user3):
    # add another post, add a comment on it for distraction
    post_other = post_manager.add_post(user, 'pid-other', PostType.TEXT_ONLY, text='go go')
    comment_other = comment_manager.add_comment('coid', post_other.id, user.id, 'lore')

    # add two comments on the target post
    comment_1 = comment_manager.add_comment('cid1', post.id, user2.id, 'lore')
    comment_2 = comment_manager.add_comment('cid2', post.id, user3.id, 'lore')

    # check post, user comment count
    post.refresh_item().item.get('commentCount', 0) == 2
    user2.refresh_item().item.get('commentCount', 0) == 1
    user3.refresh_item().item.get('commentCount', 0) == 1

    # delete all the comments on the post, verify it worked
    comment_manager.delete_all_on_post(post.id)
    assert comment_manager.get_comment(comment_1.id) is None
    assert comment_manager.get_comment(comment_2.id) is None

    # verify the unrelated comment was untouched
    assert comment_manager.get_comment(comment_other.id)

    # check post comment count
    post.refresh_item().item.get('commentCount', 0) == 0
    user2.refresh_item().item.get('commentCount', 0) == 0
    user3.refresh_item().item.get('commentCount', 0) == 0


def test_record_views(comment_manager, user, user2, user3, post, caplog, card_manager):
    card_spec = CommentCardSpec(user.id, post.id)
    comment1 = comment_manager.add_comment(str(uuid.uuid4()), post.id, user2.id, 't')
    comment2 = comment_manager.add_comment(str(uuid.uuid4()), post.id, user2.id, 't')

    # cant record view to comment that dne
    with caplog.at_level(logging.WARNING):
        comment_manager.record_views(['cid-dne'], user2.id)
    assert len(caplog.records) == 1
    assert 'cid-dne' in caplog.records[0].msg
    assert user2.id in caplog.records[0].msg

    # recording views to our own is a no-op
    assert comment_manager.view_dynamo.get_view(comment1.id, user2.id) is None
    assert comment_manager.view_dynamo.get_view(comment2.id, user2.id) is None
    comment_manager.record_views([comment1.id, comment2.id], user2.id)
    assert comment_manager.view_dynamo.get_view(comment1.id, user2.id) is None
    assert comment_manager.view_dynamo.get_view(comment2.id, user2.id) is None

    # another user can record views of our comments, which does not clear the 'coment activity' indicators
    post.card_manager.add_card_by_spec_if_dne(card_spec)
    post.dynamo.set_last_unviewed_comment_at(post.item, pendulum.now('utc'))
    assert post.refresh_item().item['gsiA3SortKey']
    assert card_manager.get_card(card_spec.card_id)
    assert comment_manager.view_dynamo.get_view(comment1.id, user3.id) is None
    assert comment_manager.view_dynamo.get_view(comment2.id, user3.id) is None
    comment_manager.record_views([comment1.id, comment2.id, comment1.id], user3.id)
    assert comment_manager.view_dynamo.get_view(comment1.id, user3.id)['viewCount'] == 2
    assert comment_manager.view_dynamo.get_view(comment2.id, user3.id)['viewCount'] == 1
    assert post.refresh_item().item['gsiA3SortKey']
    assert card_manager.get_card(card_spec.card_id)

    # post owner records views of comment, clears 'comment activity' indicators
    assert post.refresh_item().item['gsiA3SortKey']
    assert card_manager.get_card(card_spec.card_id)
    assert comment_manager.view_dynamo.get_view(comment1.id, user.id) is None
    assert comment_manager.view_dynamo.get_view(comment2.id, user.id) is None
    comment_manager.record_views([comment1.id, comment2.id, comment1.id], user.id)
    assert comment_manager.view_dynamo.get_view(comment1.id, user.id)['viewCount'] == 2
    assert comment_manager.view_dynamo.get_view(comment2.id, user.id)['viewCount'] == 1
    post.refresh_item().item.get('hasNewCommentActivity', False) is False
    assert 'gsiA3SortKey' not in post.refresh_item().item
    assert card_manager.get_card(card_spec.card_id) is None
