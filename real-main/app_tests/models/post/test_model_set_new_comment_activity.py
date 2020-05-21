import unittest.mock as mock

import pytest

from app.models.post.enums import PostType


@pytest.fixture
def user(user_manager, cognito_client):
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username='pbuid')
    yield user_manager.create_cognito_only_user('pbuid', 'pbUname')


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user, 'pid1', PostType.TEXT_ONLY, text='t')


@pytest.fixture
def post2(post_manager, user):
    yield post_manager.add_post(user, 'pid2', PostType.TEXT_ONLY, text='t')


def test_set_new_comment_activity_noop(post):
    post.dynamo = mock.Mock()
    post.user_manager = mock.Mock()

    # verify setting False when doesn't exist does nothing with dynamo
    post.set_new_comment_activity(False)
    assert 'hasNewCommentActivity' not in post.item
    assert post.dynamo.mock_calls == []
    assert post.user_manager.mock_calls == []

    # verify setting False when is already False does nothing with dynamo
    post.item['hasNewCommentActivity'] = False
    post.set_new_comment_activity(False)
    assert post.item['hasNewCommentActivity'] is False
    assert post.dynamo.mock_calls == []
    assert post.user_manager.mock_calls == []

    # verify setting True when is already True does nothing with dynamo
    post.item['hasNewCommentActivity'] = True
    post.set_new_comment_activity(True)
    assert post.item['hasNewCommentActivity'] is True
    assert post.dynamo.mock_calls == []
    assert post.user_manager.mock_calls == []


def test_set_new_comment_activity_basic_add_remove(user, post, post2):
    assert 'postHasNewCommentActivityCount' not in user.item
    assert 'hasNewCommentActivity' not in post.item
    assert 'hasNewCommentActivity' not in post2.item

    # verify we add comment activity correctly
    post.set_new_comment_activity(True)
    assert post.item['hasNewCommentActivity'] is True
    user.refresh_item()
    assert user.item['postHasNewCommentActivityCount'] == 1

    post2.set_new_comment_activity(True)
    assert post2.item['hasNewCommentActivity'] is True
    user.refresh_item()
    assert user.item['postHasNewCommentActivityCount'] == 2

    # verify we remove comment activity correctly
    post.set_new_comment_activity(False)
    assert post.item['hasNewCommentActivity'] is False
    user.refresh_item()
    assert user.item['postHasNewCommentActivityCount'] == 1

    post2.set_new_comment_activity(False)
    assert post2.item['hasNewCommentActivity'] is False
    user.refresh_item()
    assert user.item['postHasNewCommentActivityCount'] == 0


def test_set_new_comment_activity_race_condition_new_activity(user, post):
    assert 'postHasNewCommentActivityCount' not in user.item
    assert 'hasNewCommentActivity' not in post.item

    # sneak behind in mem values and alter dynamo directly
    transacts = [
        post.dynamo.transact_set_has_new_comment_activity(post.id, True),
        user.dynamo.transact_increment_post_has_new_comment_activity_count(user.id),
    ]
    post.dynamo.client.transact_write_items(transacts)
    assert post.dynamo.get_post(post.id)['hasNewCommentActivity'] is True
    assert user.dynamo.get_user(user.id)['postHasNewCommentActivityCount'] == 1

    # simulated race condition on setting to True, verify dynamo ends as we expect
    post.set_new_comment_activity(True)
    assert post.item['hasNewCommentActivity'] is True
    post.refresh_item()
    assert post.item['hasNewCommentActivity'] is True
    user.refresh_item()
    assert user.item['postHasNewCommentActivityCount'] == 1

    # set up another simulated race condition
    # this post has already been set to no activity, and some other post of ours has
    # activity (hence our activity counter is not at zero)
    transacts = [post.dynamo.transact_set_has_new_comment_activity(post.id, False)]
    post.dynamo.client.transact_write_items(transacts)
    assert post.dynamo.get_post(post.id)['hasNewCommentActivity'] is False
    assert user.dynamo.get_user(user.id)['postHasNewCommentActivityCount'] == 1

    # simulated race condition on setting to False, verify dynamo ends as we expect
    post.set_new_comment_activity(False)
    assert post.item['hasNewCommentActivity'] is False
    post.refresh_item()
    assert post.item['hasNewCommentActivity'] is False
    user.refresh_item()
    assert user.item['postHasNewCommentActivityCount'] == 1
