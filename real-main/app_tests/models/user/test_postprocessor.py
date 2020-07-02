import logging
from unittest.mock import Mock, call
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
    # use simulated update to disable a user
    user_id = str(uuid4())
    pk = f'user/{user_id}'
    sk = 'profile'
    old_item = {'userId': {'S': user_id}}
    new_item = {'userId': {'S': user_id}}

    user_postprocessor.handle_elasticsearch = Mock(user_postprocessor.handle_elasticsearch)
    user_postprocessor.handle_pinpoint = Mock(user_postprocessor.handle_pinpoint)
    user_postprocessor.handle_requested_followers_card = Mock(user_postprocessor.handle_requested_followers_card)
    user_postprocessor.handle_chats_with_new_messages_card = Mock(
        user_postprocessor.handle_chats_with_new_messages_card
    )
    user_postprocessor.run(pk, sk, old_item, new_item)
    assert user_postprocessor.handle_elasticsearch.mock_calls == [call(user_id, old_item, new_item)]
    assert user_postprocessor.handle_pinpoint.mock_calls == [call(user_id, old_item, new_item)]
    assert user_postprocessor.handle_requested_followers_card.mock_calls == [call(user_id, old_item, new_item)]
    assert user_postprocessor.handle_chats_with_new_messages_card.mock_calls == [
        call(user_id, old_item, new_item)
    ]


@pytest.mark.parametrize(
    'method_name, attribute_name',
    [
        ['forced_comment_deletion', 'commentForcedDeletionCount'],
        ['forced_post_archiving', 'postForcedArchivingCount'],
    ],
)
def test_run_calls_forced_X(user_postprocessor, method_name, attribute_name):
    pk, sk = f'user/{uuid4()}', 'profile'
    setattr(user_postprocessor, method_name, Mock(getattr(user_postprocessor, method_name)))
    assert getattr(user_postprocessor, method_name).mock_calls == []

    # cases where it should not be called
    user_postprocessor.run(pk, sk, {}, {})
    user_postprocessor.run(pk, sk, {}, {attribute_name: 0})
    user_postprocessor.run(pk, sk, {attribute_name: 0}, {})
    user_postprocessor.run(pk, sk, {attribute_name: 0}, {attribute_name: 0})
    user_postprocessor.run(pk, sk, {attribute_name: 1}, {attribute_name: 1})
    user_postprocessor.run(pk, sk, {attribute_name: 1}, {attribute_name: 0})
    user_postprocessor.run(pk, sk, {attribute_name: 2}, {attribute_name: 0})
    user_postprocessor.run(pk, sk, {attribute_name: 2}, {attribute_name: 2})

    # cases where it should be called
    user_postprocessor.run(pk, sk, {}, {attribute_name: 1})
    assert getattr(user_postprocessor, method_name).mock_calls == [call({attribute_name: 1})]

    getattr(user_postprocessor, method_name).reset_mock()
    user_postprocessor.run(pk, sk, {attribute_name: 0}, {attribute_name: 1})
    assert getattr(user_postprocessor, method_name).mock_calls == [call({attribute_name: 1})]

    getattr(user_postprocessor, method_name).reset_mock()
    user_postprocessor.run(pk, sk, {attribute_name: 1}, {attribute_name: 2})
    assert getattr(user_postprocessor, method_name).mock_calls == [call({attribute_name: 2})]

    getattr(user_postprocessor, method_name).reset_mock()
    user_postprocessor.run(pk, sk, {attribute_name: 1}, {attribute_name: 3, 'other': 'lore'})
    assert getattr(user_postprocessor, method_name).mock_calls == [call({attribute_name: 3, 'other': 'lore'})]


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


def test_forced_comment_deletion_unmet(user_postprocessor, user, caplog):
    user.is_forced_disabling_criteria_met_by_comments = Mock(return_value=False)
    user.disable = Mock()
    user_postprocessor.manager.init_user = Mock(return_value=user)

    with caplog.at_level(logging.WARNING):
        user_postprocessor.forced_comment_deletion(user.item)
    assert caplog.records == []
    assert user.disable.mock_calls == []


def test_forced_comment_deletion_met(user_postprocessor, user, caplog):
    user.is_forced_disabling_criteria_met_by_comments = Mock(return_value=True)
    user.disable = Mock()
    user_postprocessor.manager.init_user = Mock(return_value=user)

    with caplog.at_level(logging.WARNING):
        user_postprocessor.forced_comment_deletion(user.item)
    assert len(caplog.records) == 1
    assert 'USER_FORCE_DISABLED' in caplog.records[0].msg
    assert user.id in caplog.records[0].msg
    assert 'due to comments' in caplog.records[0].msg
    assert user.disable.mock_calls == [call()]


def test_forced_post_archiving_unmet(user_postprocessor, user, caplog):
    user.is_forced_disabling_criteria_met_by_posts = Mock(return_value=False)
    user.disable = Mock()
    user_postprocessor.manager.init_user = Mock(return_value=user)

    with caplog.at_level(logging.WARNING):
        user_postprocessor.forced_post_archiving(user.item)
    assert caplog.records == []
    assert user.disable.mock_calls == []


def test_forced_post_archiving_met(user_postprocessor, user, caplog):
    user.is_forced_disabling_criteria_met_by_posts = Mock(return_value=True)
    user.disable = Mock()
    user_postprocessor.manager.init_user = Mock(return_value=user)

    with caplog.at_level(logging.WARNING):
        user_postprocessor.forced_post_archiving(user.item)
    assert len(caplog.records) == 1
    assert 'USER_FORCE_DISABLED' in caplog.records[0].msg
    assert user.id in caplog.records[0].msg
    assert 'due to posts' in caplog.records[0].msg
    assert user.disable.mock_calls == [call()]
