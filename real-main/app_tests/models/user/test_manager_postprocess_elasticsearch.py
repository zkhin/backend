from unittest.mock import call
from uuid import uuid4

import pendulum
import pytest


@pytest.fixture
def user_id():
    yield str(uuid4())


def test_postprocess_elasticsearch_new_user(user_manager, user_id):
    old_item = {}
    new_item = {'userId': user_id}

    user_manager.elasticsearch_client.reset_mock()
    user_manager.postprocess_elasticsearch(old_item, new_item)
    assert user_manager.elasticsearch_client.mock_calls == [call.add_user(user_id, new_item)]


def test_postprocess_elasticsearch_updated_user(user_manager, user_id):
    old_item = {'userId': user_id}
    new_item = {'userId': user_id}

    user_manager.elasticsearch_client.reset_mock()
    user_manager.postprocess_elasticsearch(old_item, new_item)
    assert user_manager.elasticsearch_client.mock_calls == [call.update_user(user_id, old_item, new_item)]


def test_postprocess_elasticsearch_deleted_user(user_manager, user_id):
    old_item = {'userId': user_id}
    new_item = {}

    user_manager.elasticsearch_client.reset_mock()
    user_manager.postprocess_elasticsearch(old_item, new_item)
    assert user_manager.elasticsearch_client.mock_calls == [call.delete_user(user_id)]


def test_postprocess_elasticsearch_manual_reindexing(user_manager, user_id):
    # verify first manual reindexing re-adds all users
    old_item = {'userId': user_id}
    new_item = {'userId': user_id, 'lastManuallyReindexedAt': pendulum.now('utc').to_iso8601_string()}
    user_manager.elasticsearch_client.reset_mock()
    user_manager.postprocess_elasticsearch(old_item, new_item)
    assert user_manager.elasticsearch_client.mock_calls == [call.add_user(user_id, new_item)]

    # verify subsequent manual reindexing re-adds all users again
    old_item = new_item
    new_item = {'userId': user_id, 'lastManuallyReindexedAt': pendulum.now('utc').to_iso8601_string()}
    user_manager.elasticsearch_client.reset_mock()
    user_manager.postprocess_elasticsearch(old_item, new_item)
    assert user_manager.elasticsearch_client.mock_calls == [call.add_user(user_id, new_item)]
