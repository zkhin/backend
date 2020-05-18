import unittest.mock as mock
import uuid

import pytest

import app.models.comment.exceptions as comment_exceptions
import app.models.post.enums as post_enums


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username=user_id)
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def comment(post_manager, comment_manager, user):
    post = post_manager.add_post(user.id, str(uuid.uuid4()), post_enums.PostType.TEXT_ONLY, text='t')
    yield comment_manager.add_comment(str(uuid.uuid4()), post.id, user.id, 'lore ipsum')


user2 = user
user3 = user


def test_remove_from_flagging(comment):
    comment.delete = mock.Mock()
    comment.remove_from_flagging()
    assert comment.delete.mock_calls == [mock.call(forced=True)]


def test_is_user_forced_disabling_criteria_met(comment):
    return_value = {}
    comment.user.is_forced_disabling_criteria_met_by_comments = mock.Mock(return_value=return_value)
    assert comment.is_user_forced_disabling_criteria_met() is return_value


def test_cant_flag_comment_on_post_of_unfollowed_private_user(comment, user, user2, user3, follow_manager):
    # set the post owner to private, verify user3 can't flag
    user.set_privacy_status(user.enums.UserPrivacyStatus.PRIVATE)
    with pytest.raises(comment_exceptions.CommentException, match='not have access'):
        comment.flag(user3)

    # request to follow - verify still can't flag
    following = follow_manager.request_to_follow(user3, user)
    with pytest.raises(comment_exceptions.CommentException, match='not have access'):
        comment.flag(user3)

    # deny the follow request - still can't flag
    following.deny()
    with pytest.raises(comment_exceptions.CommentException, match='not have access'):
        comment.flag(user3)

    # check no flags
    assert comment.item.get('flagCount', 0) == 0
    assert comment.refresh_item().item.get('flagCount', 0) == 0
    assert list(comment.flag_dynamo.generate_by_item(comment.id)) == []

    # accept the follow request - now can flag
    following.accept()
    comment.flag(user3)

    # check the flag exists
    assert comment.item.get('flagCount', 0) == 1
    assert comment.refresh_item().item.get('flagCount', 0) == 1
    assert len(list(comment.flag_dynamo.generate_by_item(comment.id))) == 1
