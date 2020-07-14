from unittest.mock import Mock, call, patch
from uuid import uuid4

import pytest

from app.models.post.enums import PostType


@pytest.fixture
def comment_postprocessor(comment_manager):
    yield comment_manager.postprocessor


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
def comment(comment_manager, post, user2):
    yield comment_manager.add_comment(str(uuid4()), post.id, user2.id, 'lore ipsum')


def test_run_view(comment_postprocessor, comment, post, user2, user):
    pk, sk = comment.item['partitionKey'], comment.item['sortKey']

    # simulate a comment view, verify calls
    comment.record_view_count(user.id, 1)
    view_item = comment.view_dynamo.get_view(comment.id, user.id)
    pk, sk = view_item['partitionKey'], view_item['sortKey']
    comment_postprocessor.post_manager = Mock(comment_postprocessor.post_manager)
    comment_postprocessor.run(pk, sk, {}, view_item)
    assert comment_postprocessor.post_manager.mock_calls == [
        call.postprocessor.comment_view_added(post.id, user.id)
    ]


def test_run_comment_flag(comment_postprocessor, comment, user2):
    # create a flag by user2
    comment.flag_dynamo.add(comment.id, user2.id)
    flag_item = comment.flag_dynamo.get(comment.id, user2.id)
    pk, sk = flag_item['partitionKey'], flag_item['sortKey']

    # commentprocess adding that comment flag, verify calls correct
    with patch.object(comment_postprocessor, 'manager') as manager_mock:
        comment_postprocessor.run(pk, sk, {}, flag_item)
    assert manager_mock.on_flag_added.mock_calls == [call(comment.id, user2.id)]
    assert manager_mock.on_flag_deleted.mock_calls == []

    # commentprocess editing that comment flag, verify calls correct
    with patch.object(comment_postprocessor, 'manager') as manager_mock:
        comment_postprocessor.run(pk, sk, flag_item, flag_item)
    assert manager_mock.on_flag_added.mock_calls == []
    assert manager_mock.on_flag_deleted.mock_calls == []

    # commentprocess deleting that comment flag, verify calls correct
    with patch.object(comment_postprocessor, 'manager') as manager_mock:
        comment_postprocessor.run(pk, sk, flag_item, {})
    assert manager_mock.on_flag_added.mock_calls == []
    assert manager_mock.on_flag_deleted.mock_calls == [call(comment.id)]
