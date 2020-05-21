import unittest.mock as mock
import uuid

import pytest

from app.models.post.enums import PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id = str(uuid.uuid4())
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username=user_id)
    yield user_manager.create_cognito_only_user(user_id, str(uuid.uuid4())[:8])


user2 = user


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user, 'pid1', PostType.TEXT_ONLY, text='t')


def test_remove_from_flagging(post):
    post.archive = mock.Mock()
    post.remove_from_flagging()
    assert post.archive.mock_calls == [mock.call(forced=True)]


def test_is_user_forced_disabling_criteria_met(post):
    return_value = {}
    post.user.is_forced_disabling_criteria_met_by_posts = mock.Mock(return_value=return_value)
    assert post.is_user_forced_disabling_criteria_met() is return_value


def test_cant_flag_post_of_private_user_we_are_not_following(post, user, user2, follow_manager):
    # can't flag post of private user we're not following
    user.set_privacy_status(user.enums.UserPrivacyStatus.PRIVATE)
    with pytest.raises(post.exceptions.PostException, match='not have access'):
        post.flag(user2)

    # request to follow - still can't flag
    following = follow_manager.request_to_follow(user2, user)
    with pytest.raises(post.exceptions.PostException, match='not have access'):
        post.flag(user2)

    # deny the follow request - still can't flag
    following.deny()
    with pytest.raises(post.exceptions.PostException, match='not have access'):
        post.flag(user2)

    # check no flags
    assert post.item.get('flagCount', 0) == 0
    assert post.refresh_item().item.get('flagCount', 0) == 0
    assert list(post.flag_dynamo.generate_by_item(post.id)) == []

    # accept the follow request - now can flag
    following.accept()
    post.flag(user2)

    # check the flag exists
    assert post.item.get('flagCount', 0) == 1
    assert post.refresh_item().item.get('flagCount', 0) == 1
    assert len(list(post.flag_dynamo.generate_by_item(post.id))) == 1
