import logging
from uuid import uuid4

import pytest

from app.models.post.enums import PostType


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


def test_on_flag_added(comment_manager, comment, user2):
    # check starting state
    assert comment.refresh_item().item.get('flagCount', 0) == 0

    # commentprocess, verify flagCount is incremented & not force deleted
    comment_manager.on_flag_added(comment.id, user2.id)
    assert comment.refresh_item().item.get('flagCount', 0) == 1


def test_on_flag_added_force_archive_by_admin(comment_manager, comment, user2, caplog):
    # configure and check starting state
    assert comment.refresh_item().item.get('flagCount', 0) == 0
    user2.update_username(comment.flag_admin_usernames[0])

    # commentprocess, verify comment is force-deleted
    with caplog.at_level(logging.WARNING):
        comment_manager.on_flag_added(comment.id, user2.id)
    assert len(caplog.records) == 1
    assert 'Force deleting comment' in caplog.records[0].msg
    assert comment.refresh_item().item is None


def test_on_flag_added_force_archive_by_crowdsourced_criteria(comment_manager, comment, user2, caplog):
    # configure and check starting state
    assert comment.refresh_item().item.get('flagCount', 0) == 0
    for _ in range(6):
        comment.post.dynamo.increment_viewed_by_count(comment.post.id)

    # commentprocess, verify flagCount is incremented and force archived
    with caplog.at_level(logging.WARNING):
        comment_manager.on_flag_added(comment.id, user2.id)
    assert len(caplog.records) == 1
    assert 'Force deleting comment' in caplog.records[0].msg
    assert comment.refresh_item().item is None
