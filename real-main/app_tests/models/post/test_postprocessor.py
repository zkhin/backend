from unittest.mock import call, patch
from uuid import uuid4

import pytest

from app.models.post.enums import PostType


@pytest.fixture
def post_postprocessor(post_manager):
    yield post_manager.postprocessor


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user, str(uuid4()), PostType.TEXT_ONLY, text='go go')


def test_run_post(post_postprocessor, post):
    pk, sk = post.item['partitionKey'], post.item['sortKey']
    old_item, new_item = post.item.copy(), post.item.copy()

    # test an edit
    with patch.object(post_postprocessor, 'manager') as manager_mock:
        post_postprocessor.run(pk, sk, old_item, new_item)
    assert manager_mock.mock_calls == []

    # test an add
    with patch.object(post_postprocessor, 'manager') as manager_mock:
        post_postprocessor.run(pk, sk, {}, new_item)
    assert manager_mock.mock_calls == []

    # test a delete
    with patch.object(post_postprocessor, 'manager') as manager_mock:
        post_postprocessor.run(pk, sk, old_item, {})
    assert manager_mock.mock_calls == []


def test_run_post_flag(post_postprocessor, post, user2):
    # create a flag by user2
    post.flag_dynamo.add(post.id, user2.id)
    flag_item = post.flag_dynamo.get(post.id, user2.id)
    pk, sk = flag_item['partitionKey'], flag_item['sortKey']

    # postprocess adding that post flag, verify calls correct
    with patch.object(post_postprocessor, 'manager') as manager_mock:
        post_postprocessor.run(pk, sk, {}, flag_item)
    assert manager_mock.on_flag_added.mock_calls == [call(post.id, user2.id)]
    assert manager_mock.on_flag_deleted.mock_calls == []

    # postprocess editing that post flag, verify calls correct
    with patch.object(post_postprocessor, 'manager') as manager_mock:
        post_postprocessor.run(pk, sk, flag_item, flag_item)
    assert manager_mock.on_flag_added.mock_calls == []
    assert manager_mock.on_flag_deleted.mock_calls == []

    # postprocess deleting that post flag, verify calls correct
    with patch.object(post_postprocessor, 'manager') as manager_mock:
        post_postprocessor.run(pk, sk, flag_item, {})
    assert manager_mock.on_flag_added.mock_calls == []
    assert manager_mock.on_flag_deleted.mock_calls == [call(post.id)]
