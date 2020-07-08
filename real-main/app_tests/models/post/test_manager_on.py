import logging
from uuid import uuid4

import pytest

from app.models.post.enums import PostStatus, PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user, str(uuid4()), PostType.TEXT_ONLY, text='go go')


def test_on_flag_added(post_manager, post, user2):
    # check starting state
    assert post.refresh_item().item.get('flagCount', 0) == 0

    # postprocess, verify flagCount is incremented & not force achived
    post_manager.on_flag_added(post.id, user2.id)
    assert post.refresh_item().item.get('flagCount', 0) == 1
    assert post.status != PostStatus.ARCHIVED


def test_on_flag_added_force_archive_by_admin(post_manager, post, user2, caplog):
    # configure and check starting state
    assert post.refresh_item().item.get('flagCount', 0) == 0
    user2.update_username(post.flag_admin_usernames[0])

    # postprocess, verify flagCount is incremented and force archived
    with caplog.at_level(logging.WARNING):
        post_manager.on_flag_added(post.id, user2.id)
    assert len(caplog.records) == 1
    assert 'Force archiving post' in caplog.records[0].msg
    assert post.refresh_item().item.get('flagCount', 0) == 1
    assert post.status == PostStatus.ARCHIVED


def test_on_flag_added_force_archive_by_crowdsourced_criteria(post_manager, post, user2, caplog):
    # configure and check starting state
    assert post.refresh_item().item.get('flagCount', 0) == 0
    for _ in range(6):
        post.dynamo.increment_viewed_by_count(post.id)

    # postprocess, verify flagCount is incremented and force archived
    with caplog.at_level(logging.WARNING):
        post_manager.on_flag_added(post.id, user2.id)
    assert len(caplog.records) == 1
    assert 'Force archiving post' in caplog.records[0].msg
    assert post.refresh_item().item.get('flagCount', 0) == 1
    assert post.status == PostStatus.ARCHIVED
