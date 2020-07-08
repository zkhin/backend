import logging
from unittest.mock import call, patch
from uuid import uuid4

import pytest


@pytest.fixture
def user_postprocessor(user_manager):
    yield user_manager.postprocessor


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


def test_run(user_postprocessor):
    user_id = str(uuid4())
    pk = f'user/{user_id}'
    sk = 'profile'
    old_item = {'userId': {'S': user_id}}
    new_item = {'userId': {'S': user_id}}

    with pytest.raises(AssertionError):
        user_postprocessor.run(pk, 'wrong-sk', old_item, new_item)

    # test an edit
    with patch.object(user_postprocessor, 'manager') as manager_mock:
        user_postprocessor.run(pk, sk, old_item, new_item)
    assert manager_mock.mock_calls == [call.init_user(new_item), call.init_user().on_add_or_edit(old_item)]

    # test an add
    with patch.object(user_postprocessor, 'manager') as manager_mock:
        user_postprocessor.run(pk, sk, None, new_item)
    assert manager_mock.mock_calls == [call.init_user(new_item), call.init_user().on_add_or_edit(None)]

    # test a delete
    with patch.object(user_postprocessor, 'manager') as manager_mock:
        user_postprocessor.run(pk, sk, old_item, None)
    assert manager_mock.mock_calls == [call.init_user(old_item), call.init_user().on_delete()]


def test_comment_added(user_postprocessor, user):
    # check & save starting state
    org_item = user.refresh_item().item
    assert 'commentCount' not in org_item

    # process, check state
    user_postprocessor.comment_added(user.id)
    assert user.refresh_item().item['commentCount'] == 1

    # process, check state
    user_postprocessor.comment_added(user.id)
    assert user.refresh_item().item['commentCount'] == 2

    # check for unexpected state changes
    new_item = user.item
    new_item.pop('commentCount')
    assert new_item == org_item


def test_comment_deleted(user_postprocessor, user, caplog):
    # configure, check & save starting state
    user_postprocessor.comment_added(user.id)
    org_item = user.refresh_item().item
    assert org_item['commentCount'] == 1
    assert 'commentDeletedCount' not in org_item

    # process, check state
    user_postprocessor.comment_deleted(user.id)
    new_item = user.refresh_item().item
    assert new_item['commentCount'] == 0
    assert new_item['commentDeletedCount'] == 1

    # process again, verify fails softly
    with caplog.at_level(logging.WARNING):
        user_postprocessor.comment_deleted(user.id)
    assert len(caplog.records) == 1
    assert 'Failed to decrement' in caplog.records[0].msg
    assert 'commentCount' in caplog.records[0].msg
    assert user.id in caplog.records[0].msg
    new_item = user.refresh_item().item
    assert new_item['commentCount'] == 0
    assert new_item['commentDeletedCount'] == 2

    # check for unexpected state changes
    del new_item['commentCount'], org_item['commentCount'], new_item['commentDeletedCount']
    assert new_item == org_item
