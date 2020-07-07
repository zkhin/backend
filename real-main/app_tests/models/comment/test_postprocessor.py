import logging
from unittest.mock import Mock, call
from uuid import uuid4

import pendulum
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


def test_run(comment_postprocessor, comment, post, user2, user):
    pk, sk = comment.item['partitionKey'], comment.item['sortKey']
    commented_at = pendulum.parse(comment.item['commentedAt'])

    # simulate a new comment, verify calls
    old_item = {}
    new_item = comment.refresh_item().item
    comment_postprocessor.post_manager = Mock(comment_postprocessor.post_manager)
    comment_postprocessor.user_manager = Mock(comment_postprocessor.user_manager)
    comment_postprocessor.run(pk, sk, old_item, new_item)
    assert comment_postprocessor.post_manager.mock_calls == [
        call.postprocessor.comment_added(post.id, user2.id, commented_at)
    ]
    assert comment_postprocessor.user_manager.mock_calls == [call.postprocessor.comment_added(user2.id)]

    # simulate a editing a comment, verify no calls
    old_item = new_item
    new_item = comment.refresh_item().item
    comment_postprocessor.post_manager = Mock(comment_postprocessor.post_manager)
    comment_postprocessor.user_manager = Mock(comment_postprocessor.user_manager)
    comment_postprocessor.run(pk, sk, old_item, new_item)
    assert comment_postprocessor.post_manager.mock_calls == []
    assert comment_postprocessor.user_manager.mock_calls == []

    # simulate a deleteing a comment, verify calls
    old_item = new_item
    new_item = {}
    comment_postprocessor.post_manager = Mock(comment_postprocessor.post_manager)
    comment_postprocessor.user_manager = Mock(comment_postprocessor.user_manager)
    comment_postprocessor.run(pk, sk, old_item, new_item)
    assert comment_postprocessor.post_manager.mock_calls == [
        call.postprocessor.comment_deleted(post.id, comment.id, user2.id, commented_at)
    ]
    assert comment_postprocessor.user_manager.mock_calls == [call.postprocessor.comment_deleted(user2.id)]

    # simulate a comment view, verify calls
    comment.record_view_count(user.id, 1)
    view_item = comment.view_dynamo.get_view(comment.id, user.id)
    pk, sk = view_item['partitionKey'], view_item['sortKey']
    comment_postprocessor.post_manager = Mock(comment_postprocessor.post_manager)
    comment_postprocessor.user_manager = Mock(comment_postprocessor.user_manager)
    comment_postprocessor.run(pk, sk, {}, view_item)
    assert comment_postprocessor.post_manager.mock_calls == [
        call.postprocessor.comment_view_added(post.id, user.id)
    ]
    assert comment_postprocessor.user_manager.mock_calls == []


def test_run_comment_flag(comment_postprocessor, comment, user2):
    # create a flag by user2
    comment.flag_dynamo.add(comment.id, user2.id)
    flag_item = comment.flag_dynamo.get(comment.id, user2.id)
    pk, sk = flag_item['partitionKey'], flag_item['sortKey']

    # set up mocks
    comment_postprocessor.comment_flag_added = Mock()
    comment_postprocessor.comment_flag_deleted = Mock()

    # commentprocess adding that comment flag, verify calls correct
    comment_postprocessor.run(pk, sk, {}, flag_item)
    assert comment_postprocessor.comment_flag_added.mock_calls == [call(comment.id, user2.id)]
    assert comment_postprocessor.comment_flag_deleted.mock_calls == []

    # reset mocks
    comment_postprocessor.comment_flag_added = Mock()
    comment_postprocessor.comment_flag_deleted = Mock()

    # commentprocess editing that comment flag, verify calls correct
    comment_postprocessor.run(pk, sk, flag_item, flag_item)
    assert comment_postprocessor.comment_flag_added.mock_calls == []
    assert comment_postprocessor.comment_flag_deleted.mock_calls == []

    # commentprocess deleting that comment flag, verify calls correct
    comment_postprocessor.run(pk, sk, flag_item, {})
    assert comment_postprocessor.comment_flag_added.mock_calls == []
    assert comment_postprocessor.comment_flag_deleted.mock_calls == [call(comment.id)]


def test_comment_flag_added(comment_postprocessor, comment, user2):
    # check starting state
    assert comment.refresh_item().item.get('flagCount', 0) == 0

    # commentprocess, verify flagCount is incremented & not force deleted
    comment_postprocessor.comment_flag_added(comment.id, user2.id)
    assert comment.refresh_item().item.get('flagCount', 0) == 1


def test_comment_flag_added_force_archive_by_admin(comment_postprocessor, comment, user2, caplog):
    # configure and check starting state
    assert comment.refresh_item().item.get('flagCount', 0) == 0
    user2.update_username(comment.flag_admin_usernames[0])

    # commentprocess, verify comment is force-deleted
    with caplog.at_level(logging.WARNING):
        comment_postprocessor.comment_flag_added(comment.id, user2.id)
    assert len(caplog.records) == 1
    assert 'Force deleting comment' in caplog.records[0].msg
    assert comment.refresh_item().item is None


def test_comment_flag_added_force_archive_by_crowdsourced_criteria(comment_postprocessor, comment, user2, caplog):
    # configure and check starting state
    assert comment.refresh_item().item.get('flagCount', 0) == 0
    for _ in range(6):
        comment.post.dynamo.increment_viewed_by_count(comment.post.id)

    # commentprocess, verify flagCount is incremented and force archived
    with caplog.at_level(logging.WARNING):
        comment_postprocessor.comment_flag_added(comment.id, user2.id)
    assert len(caplog.records) == 1
    assert 'Force deleting comment' in caplog.records[0].msg
    assert comment.refresh_item().item is None


def test_comment_flag_deleted(comment_postprocessor, comment, user2, caplog):
    # configure and check starting state
    comment_postprocessor.comment_flag_added(comment.id, user2.id)
    assert comment.refresh_item().item.get('flagCount', 0) == 1

    # commentprocess, verify flagCount is decremented
    comment_postprocessor.comment_flag_deleted(comment.id)
    assert comment.refresh_item().item.get('flagCount', 0) == 0

    # commentprocess again, verify fails softly
    with caplog.at_level(logging.WARNING):
        comment_postprocessor.comment_flag_deleted(comment.id)
    assert len(caplog.records) == 1
    assert 'Failed to decrement flagCount' in caplog.records[0].msg
    assert comment.refresh_item().item.get('flagCount', 0) == 0
