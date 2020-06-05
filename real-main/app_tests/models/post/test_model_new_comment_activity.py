import uuid
from unittest import mock

import pendulum
import pytest

from app.models.post.enums import PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user, str(uuid.uuid4()), PostType.TEXT_ONLY, text='t')


def test_clear_new_comment_activity(post):
    assert post.last_new_comment_activity_at is None

    # add some activity
    post.register_new_comment_activity()
    assert post.last_new_comment_activity_at

    # clear it
    post.clear_new_comment_activity()
    assert post.last_new_comment_activity_at is None

    # no-op: clear activity when none exists
    post.dynamo = mock.Mock()
    post_item = post.item
    post.clear_new_comment_activity()
    assert post.last_new_comment_activity_at is None
    assert post.item is post_item
    assert post.dynamo.mock_calls == []


def test_register_new_comment_activity(post):
    assert post.last_new_comment_activity_at is None

    # add some activity
    before = pendulum.now('utc')
    post.register_new_comment_activity()
    after = pendulum.now('utc')
    assert post.user_id in post.item['gsiA3PartitionKey']
    assert post.last_new_comment_activity_at > before
    assert post.last_new_comment_activity_at < after

    # update that activity
    now = pendulum.now('utc')
    post.register_new_comment_activity(now=now)
    assert post.user_id in post.item['gsiA3PartitionKey']
    assert post.last_new_comment_activity_at == now
