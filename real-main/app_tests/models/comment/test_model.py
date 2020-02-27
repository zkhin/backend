import pytest

from app.models.post.enums import PostType


@pytest.fixture
def user(user_manager):
    yield user_manager.create_cognito_only_user('pbuid', 'pbUname')


@pytest.fixture
def comment(user, post_manager, comment_manager):
    post = post_manager.add_post(user.id, 'pid', PostType.TEXT_ONLY, text='go go')
    yield comment_manager.add_comment('cid', post.id, user.id, 'run far')


def test_serialize(comment, user):
    resp = comment.serialize('caller-uid')
    assert resp.pop('commentedBy')['userId'] == user.id
    assert resp == comment.item


def test_delete(comment, post_manager):
    # verify it's visible in the DB
    comment_item = comment.dynamo.get_comment(comment.id)
    assert comment_item['commentId'] == comment.id

    # check the post's comment count
    post = post_manager.get_post(comment.item['postId'])
    assert post.item['commentCount'] == 1

    # delete the comment
    comment.delete()

    # verify in-memory item still exists, but not in DB anymore
    assert comment.item['commentId'] == comment.id
    assert comment.dynamo.get_comment(comment.id) is None

    # check the post's comment count has decremented
    post = post_manager.get_post(comment.item['postId'])
    assert post.item['commentCount'] == 0


def test_delete_cant_decrement_post_comment_count_below_zero(comment, post_manager):
    # sneak behind the model and lower the post's comment count
    transacts = [post_manager.dynamo.transact_decrement_comment_count(comment.item['postId'])]
    post_manager.dynamo.client.transact_write_items(transacts)

    # deleting the comment should fail
    with pytest.raises(comment.dynamo.client.exceptions.ConditionalCheckFailedException):
        comment.delete()

    # verify the comment is still in the DB
    comment_item = comment.dynamo.get_comment(comment.id)
    assert comment_item['commentId'] == comment.id
