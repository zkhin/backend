import pendulum
import pytest


@pytest.fixture
def user(user_manager):
    yield user_manager.create_cognito_only_user('pbuid', 'pbUname')


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user.id, 'pid', text='go go')


def test_add_comment(comment_manager, user, post):
    comment_id = 'cid'

    # check our starting state
    assert post.item.get('commentCount', 0) == 0
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

    # check the post counter incremented
    post.refresh_item()
    assert post.item['commentCount'] == 1


def test_add_comment_cant_reuse_ids(comment_manager, user, post):
    comment_id = 'cid'
    text = 'lore'

    # add a comment, verify
    comment = comment_manager.add_comment(comment_id, post.id, user.id, text)
    assert comment.id == comment_id
    post.refresh_item()
    assert post.item['commentCount'] == 1

    # verify we can't add another
    with pytest.raises(comment_manager.exceptions.CommentException):
        comment_manager.add_comment(comment_id, post.id, user.id, text)

    post.refresh_item()
    assert post.item['commentCount'] == 1


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


def test_cant_comment_if_block_exists_with_post_owner(comment_manager, user, post, block_manager, user_manager):
    comment_id = 'cid'
    commenter = user_manager.create_cognito_only_user('cuid', 'cUname')

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


def test_non_follower_cant_comment_if_private_post_owner(comment_manager, user, post, follow_manager, user_manager):
    comment_id = 'cid'
    commenter = user_manager.create_cognito_only_user('cuid', 'cUname')

    # post owner goes private
    user.set_privacy_status(user_manager.enums.UserPrivacyStatus.PRIVATE)

    # verify we can't comment on their post
    with pytest.raises(comment_manager.exceptions.CommentException):
        comment_manager.add_comment(comment_id, post.id, commenter.id, 't')

    # request to follow, verify can't comment
    follow_manager.request_to_follow(commenter, user)
    with pytest.raises(comment_manager.exceptions.CommentException):
        comment_manager.add_comment(comment_id, post.id, commenter.id, 't')

    # deny the follow request, verify can't comment
    follow_manager.deny_follow_request(commenter.id, user.id)
    with pytest.raises(comment_manager.exceptions.CommentException):
        comment_manager.add_comment(comment_id, post.id, commenter.id, 't')

    # accept the follow request, verify can comment
    follow_manager.accept_follow_request(commenter.id, user.id)
    comment = comment_manager.add_comment(comment_id, post.id, commenter.id, 't')
    assert comment.id == comment_id


def test_private_user_can_comment_on_own_post(comment_manager, user, post):
    comment_id = 'cid'

    # post owner goes private
    user.set_privacy_status(user.enums.UserPrivacyStatus.PRIVATE)

    comment = comment_manager.add_comment(comment_id, post.id, user.id, 't')
    assert comment.id == comment_id


def test_owner_of_comment_can_delete_it(comment_manager, user, post):
    comment_id = 'cid'
    comment_manager.add_comment(comment_id, post.id, user.id, text='t')

    # verify we see the comment in the DB
    comment_item = comment_manager.dynamo.get_comment(comment_id)
    assert comment_item['commentId'] == comment_id

    # owner of comment deletes it
    comment = comment_manager.delete_comment(comment_id, user.id)
    assert comment.id == comment_id

    # verify comment is no longer in db
    assert comment_manager.dynamo.get_comment(comment_id) is None


def test_owner_of_post_can_delete_comment_on_their_post(comment_manager, user, post):
    comment_id = 'cid'
    commenter_user_id = 'cuid'

    # other user adds a comment to post
    comment_manager.add_comment(comment_id, post.id, commenter_user_id, text='t')

    # verify we see the comment in the DB
    comment_item = comment_manager.dynamo.get_comment(comment_id)
    assert comment_item['commentId'] == comment_id

    # owner of the post deletes it
    comment = comment_manager.delete_comment(comment_id, user.id)
    assert comment.id == comment_id

    # verify comment is no longer in db
    assert comment_manager.dynamo.get_comment(comment_id) is None


def test_rando_cannot_delete_comment(comment_manager, post):
    comment_id = 'cid'
    commenter_user_id = 'c-uid'
    rando_user_id = 'rando-uid'

    # other user adds a comment to post
    comment_manager.add_comment(comment_id, post.id, commenter_user_id, text='t')

    # verify rando can't delete the comment
    with pytest.raises(comment_manager.exceptions.CommentException):
        comment_manager.delete_comment(comment_id, rando_user_id)

    # verify we still see the comment in the DB
    comment_item = comment_manager.dynamo.get_comment(comment_id)
    assert comment_item['commentId'] == comment_id


def test_cant_delete_comment_that_doesnt_exist(comment_manager, user, post):
    # verify rando can't delete the comment
    with pytest.raises(comment_manager.exceptions.CommentException):
        comment_manager.delete_comment('dne-cid', user.id)


def test_delete_all_by_user(comment_manager, user, post):
    # add a comment by an unrelated user for distraction
    comment_other = comment_manager.add_comment('coid', post.id, '2uid', 'lore')

    # add two comments by our target user
    comment_1 = comment_manager.add_comment('cid1', post.id, '3uid', 'lore')
    comment_2 = comment_manager.add_comment('cid2', post.id, '3uid', 'lore')

    # check post comment count
    post.refresh_item()
    assert post.item['commentCount'] == 3

    # delete all the comments by the user, verify it worked
    comment_manager.delete_all_by_user('3uid')
    assert comment_manager.get_comment(comment_1.id) is None
    assert comment_manager.get_comment(comment_2.id) is None

    # verify the unrelated comment was untouched
    assert comment_manager.get_comment(comment_other.id)

    # check post comment count
    post.refresh_item()
    assert post.item['commentCount'] == 1


def test_delete_all_on_post(comment_manager, user, post, post_manager):
    # add another post, add a comment on it for distraction
    post_other = post_manager.add_post(user.id, 'pid-other', text='go go')
    comment_other = comment_manager.add_comment('coid', post_other.id, user.id, 'lore')

    # add two comments on the target post
    comment_1 = comment_manager.add_comment('cid1', post.id, '2uid', 'lore')
    comment_2 = comment_manager.add_comment('cid2', post.id, '3uid', 'lore')

    # check post comment count
    post.refresh_item()
    assert post.item['commentCount'] == 2

    # delete all the comments on the post, verify it worked
    comment_manager.delete_all_on_post(post.id)
    assert comment_manager.get_comment(comment_1.id) is None
    assert comment_manager.get_comment(comment_2.id) is None

    # verify the unrelated comment was untouched
    assert comment_manager.get_comment(comment_other.id)

    # check post comment count
    post.refresh_item()
    assert post.item['commentCount'] == 0
