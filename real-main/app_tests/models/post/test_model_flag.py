import uuid
from unittest import mock

import pytest

from app.models.post.enums import PostType
from app.models.post.exceptions import PostException
from app.models.user.enums import UserPrivacyStatus


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


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


def test_cant_flag_post_of_private_user_we_are_not_following(post, user, user2, follower_manager):
    # can't flag post of private user we're not following
    user.set_privacy_status(UserPrivacyStatus.PRIVATE)
    with pytest.raises(PostException, match='not have access'):
        post.flag(user2)

    # request to follow - still can't flag
    following = follower_manager.request_to_follow(user2, user)
    with pytest.raises(PostException, match='not have access'):
        post.flag(user2)

    # deny the follow request - still can't flag
    following.deny()
    with pytest.raises(PostException, match='not have access'):
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
