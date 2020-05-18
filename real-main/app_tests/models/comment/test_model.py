import pytest
import uuid

from app.models.post.enums import PostType
from app.models.view.enums import ViewedStatus


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username=user_id)
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user
user3 = user


@pytest.fixture
def comment(user, post_manager, comment_manager):
    post = post_manager.add_post(user.id, str(uuid.uuid4()), PostType.TEXT_ONLY, text='go go')
    yield comment_manager.add_comment(str(uuid.uuid4()), post.id, user.id, 'run far')


comment2 = comment


def test_serialize(comment_manager, comment, user, view_manager):
    # serialize as the comment's author
    resp = comment.serialize(user.id)
    assert resp.pop('commentedBy')['userId'] == user.id
    assert resp.pop('viewedStatus') == ViewedStatus.VIEWED
    assert resp == comment.item

    # serialize as another user that has not viewed the comment
    other_user_id = 'ouid'
    resp = comment.serialize(other_user_id)
    assert resp.pop('commentedBy')['userId'] == user.id
    assert resp.pop('viewedStatus') == ViewedStatus.NOT_VIEWED
    assert resp == comment.item

    # the other user views the comment
    view_manager.record_views('comment', [comment.id], other_user_id)

    # serialize as another user that *has* viewed the comment
    other_user_id = 'ouid'
    resp = comment.serialize(other_user_id)
    assert resp.pop('commentedBy')['userId'] == user.id
    assert resp.pop('viewedStatus') == ViewedStatus.VIEWED
    assert resp == comment.item


def test_delete(comment, post_manager, comment_manager, user, user2, user3, view_manager):
    # verify it's visible in the DB
    comment_item = comment.dynamo.get_comment(comment.id)
    assert comment_item['commentId'] == comment.id

    # check the user & post's comment count
    user.refresh_item().item.get('commentCount', 0) == 1
    post_manager.get_post(comment.item['postId']).item.get('commentCount', 0) == 1

    # add two views to the comment, verify we see them
    view_manager.record_views('comment', [comment.id], user2.id)
    view_manager.record_views('comment', [comment.id], user3.id)
    assert len(list(view_manager.dynamo.generate_views(comment.item['partitionKey']))) == 2

    # comment owner deletes the comment
    comment.delete(deleter_user_id=comment.user_id)

    # verify in-memory item still exists, but not in DB anymore
    assert comment.item['commentId'] == comment.id
    assert comment.dynamo.get_comment(comment.id) is None

    # check the user & post's comment count have decremented
    user.refresh_item().item.get('commentCount', 0) == 0
    post_manager.get_post(comment.item['postId']).item.get('commentCount', 0) == 0

    # check the two comment views have also been deleted
    assert list(view_manager.dynamo.generate_views(comment.item['partitionKey'])) == []


def test_forced_delete(comment, comment2, user):
    # verify starting counts
    user.refresh_item()
    assert user.item.get('commentCount', 0) == 2
    assert user.item.get('commentDeletedCount', 0) == 0
    assert user.item.get('commentForcedDeletionCount', 0) == 0

    # normal delete one of them, force delete the other
    comment.delete(forced=False)
    comment2.delete(forced=True)

    # verify final counts
    user.refresh_item()
    assert user.item.get('commentCount', 0) == 0
    assert user.item.get('commentDeletedCount', 0) == 2
    assert user.item.get('commentForcedDeletionCount', 0) == 1


def test_delete_cant_decrement_post_comment_count_below_zero(comment, post_manager):
    # sneak behind the model and lower the post's comment count
    transacts = [post_manager.dynamo.transact_decrement_comment_count(comment.item['postId'])]
    post_manager.dynamo.client.transact_write_items(transacts)

    # deleting the comment should fail
    with pytest.raises(comment.dynamo.client.exceptions.TransactionCanceledException):
        comment.delete(deleter_user_id=comment.user_id)

    # verify the comment is still in the DB
    comment_item = comment.dynamo.get_comment(comment.id)
    assert comment_item['commentId'] == comment.id


def test_delete_cant_decrement_user_comment_count_below_zero(comment, user_manager):
    # sneak behind the model and lower the user's comment count
    transacts = [user_manager.dynamo.transact_comment_deleted(comment.item['userId'])]
    user_manager.dynamo.client.transact_write_items(transacts)

    # deleting the comment should fail
    with pytest.raises(comment.dynamo.client.exceptions.TransactionCanceledException):
        comment.delete(deleter_user_id=comment.user_id)

    # verify the comment is still in the DB
    comment_item = comment.dynamo.get_comment(comment.id)
    assert comment_item['commentId'] == comment.id


def test_only_post_owner_and_comment_owner_can_delete_a_comment(post_manager, comment_manager, user, user2, user3):
    post = post_manager.add_post(user.id, 'pid2', PostType.TEXT_ONLY, text='go go')
    comment1 = comment_manager.add_comment('cid1', post.id, user2.id, 'run far')
    comment2 = comment_manager.add_comment('cid2', post.id, user2.id, 'run far')
    post.refresh_item()

    # clear comment activity
    post.set_new_comment_activity(False)
    post.refresh_item()
    assert post.item.get('hasNewCommentActivity', False) is False
    user.refresh_item()
    assert user.item.get('postHasNewCommentActivityCount', 0) == 0

    # verify user3 (a rando) cannot delete either of the comments
    with pytest.raises(comment_manager.exceptions.CommentException, match='not authorized to delete'):
        comment1.delete(deleter_user_id=user3.id)
    with pytest.raises(comment_manager.exceptions.CommentException, match='not authorized to delete'):
        comment2.delete(deleter_user_id=user3.id)

    assert comment1.refresh_item().item
    assert comment2.refresh_item().item

    # verify post owner can delete a comment that another user left on their post, does not reigster as new activity
    comment1.delete(deleter_user_id=user.id)
    assert comment1.refresh_item().item is None
    post.refresh_item()
    assert post.item.get('hasNewCommentActivity', False) is False
    user.refresh_item()
    assert user.item.get('postHasNewCommentActivityCount', 0) == 0

    # verify comment owner can delete their own comment, does register as new activity
    comment2.delete(deleter_user_id=user2.id)
    assert comment2.refresh_item().item is None
    post.refresh_item()
    assert post.item.get('hasNewCommentActivity', False) is True
    user.refresh_item()
    assert user.item.get('postHasNewCommentActivityCount', 0) == 1
