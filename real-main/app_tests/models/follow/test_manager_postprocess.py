import logging
from uuid import uuid4

import pytest

from app.models.follow.enums import FollowStatus


@pytest.fixture
def user1(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user1


@pytest.fixture
def follow_deets(follow_manager, user1, user2):
    item = follow_manager.dynamo.add_following(user1.id, user2.id, FollowStatus.REQUESTED)
    typed_pk = follow_manager.dynamo.typed_pk(user1.id, user2.id)
    yield (item, typed_pk, typed_pk['partitionKey']['S'], typed_pk['sortKey']['S'])


@pytest.mark.parametrize('follow_status', [FollowStatus.FOLLOWING])
def test_postprocess_add_increments(follow_manager, user1, user2, follow_deets, follow_status):
    # set up and verify starting state
    item, typed_pk, pk, sk = follow_deets
    follow_manager.dynamo.update_following_status(item, follow_status)
    old_item = None
    new_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
    assert new_item['followStatus']['S'] == follow_status
    user1.refresh_item().item.get('followedCount', 0) == 0
    user2.refresh_item().item.get('followerCount', 0) == 0

    # postprocess the add and verify final state
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    user1.refresh_item().item.get('followedCount', 0) == 1
    user2.refresh_item().item.get('followerCount', 0) == 1


@pytest.mark.parametrize('follow_status', [s for s in FollowStatus._ALL if s != FollowStatus.FOLLOWING])
def test_postprocess_add_no_change(follow_manager, user1, user2, follow_deets, follow_status):
    # set up and verify starting state
    item, typed_pk, pk, sk = follow_deets
    follow_manager.dynamo.update_following_status(item, follow_status)
    old_item = None
    new_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
    assert new_item['followStatus']['S'] == follow_status
    user1.refresh_item().item.get('followedCount', 0) == 0
    user2.refresh_item().item.get('followerCount', 0) == 0

    # postprocess the add and verify final state
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    user1.refresh_item().item.get('followedCount', 0) == 0
    user2.refresh_item().item.get('followerCount', 0) == 0


@pytest.mark.parametrize(
    'old_follow_status, new_follow_status',
    [[FollowStatus.REQUESTED, FollowStatus.FOLLOWING], [FollowStatus.DENIED, FollowStatus.FOLLOWING]],
)
def test_postprocess_update_increments(
    follow_manager, user1, user2, follow_deets, old_follow_status, new_follow_status
):
    # set up and verify starting state
    item, typed_pk, pk, sk = follow_deets
    follow_manager.dynamo.update_following_status(item, old_follow_status)
    old_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
    follow_manager.dynamo.update_following_status(item, new_follow_status)
    new_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
    assert old_item['followStatus']['S'] == old_follow_status
    assert new_item['followStatus']['S'] == new_follow_status
    user1.refresh_item().item.get('followedCount', 0) == 0
    user2.refresh_item().item.get('followerCount', 0) == 0

    # postprocess the add and verify final state
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    user1.refresh_item().item.get('followedCount', 0) == 1
    user2.refresh_item().item.get('followerCount', 0) == 1


@pytest.mark.parametrize('old_follow_status, new_follow_status', [[FollowStatus.REQUESTED, FollowStatus.DENIED]])
def test_postprocess_update_no_change(
    follow_manager, user1, user2, follow_deets, old_follow_status, new_follow_status
):
    # set up and verify starting state
    item, typed_pk, pk, sk = follow_deets
    follow_manager.dynamo.update_following_status(item, old_follow_status)
    old_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
    follow_manager.dynamo.update_following_status(item, new_follow_status)
    new_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
    assert old_item['followStatus']['S'] == old_follow_status
    assert new_item['followStatus']['S'] == new_follow_status
    user1.refresh_item().item.get('followedCount', 0) == 0
    user2.refresh_item().item.get('followerCount', 0) == 0

    # postprocess the add and verify final state
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    user1.refresh_item().item.get('followedCount', 0) == 0
    user2.refresh_item().item.get('followerCount', 0) == 0


@pytest.mark.parametrize('old_follow_status, new_follow_status', [[FollowStatus.FOLLOWING, FollowStatus.DENIED]])
def test_postprocess_update_decrements(
    follow_manager, user1, user2, follow_deets, old_follow_status, new_follow_status, caplog
):
    # postprocess an add to increment counts
    item, typed_pk, pk, sk = follow_deets
    follow_manager.dynamo.update_following_status(item, old_follow_status)
    old_item = None
    new_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
    assert new_item['followStatus']['S'] == old_follow_status
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    user1.refresh_item().item.get('followedCount', 0) == 1
    user2.refresh_item().item.get('followerCount', 0) == 1

    # postprocess the update and verify final state
    old_item = new_item
    follow_manager.dynamo.update_following_status(item, new_follow_status)
    new_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
    assert old_item['followStatus']['S'] == old_follow_status
    assert new_item['followStatus']['S'] == new_follow_status
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    user1.refresh_item().item.get('followedCount', 0) == 0
    user2.refresh_item().item.get('followerCount', 0) == 0

    # postprocess failed decrement, verify fails softly
    with caplog.at_level(logging.WARNING):
        follow_manager.postprocess_record(pk, sk, old_item, new_item)
    assert len(caplog.records) == 2
    assert all('Failed to decrement' in rec.msg for rec in caplog.records)
    assert sum('followerCount' in rec.msg for rec in caplog.records) == 1
    assert sum('followedCount' in rec.msg for rec in caplog.records) == 1
    assert sum(user1.id in rec.msg for rec in caplog.records) == 1
    assert sum(user2.id in rec.msg for rec in caplog.records) == 1
    user1.refresh_item().item.get('followedCount', 0) == 0
    user2.refresh_item().item.get('followerCount', 0) == 0


@pytest.mark.parametrize('follow_status', [FollowStatus.FOLLOWING])
def test_postprocess_delete_decrements(follow_manager, user1, user2, follow_deets, follow_status, caplog):
    # postprocess an add to increment counts
    item, typed_pk, pk, sk = follow_deets
    follow_manager.dynamo.update_following_status(item, follow_status)
    old_item = None
    new_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
    assert new_item['followStatus']['S'] == follow_status
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    user1.refresh_item().item.get('followedCount', 0) == 1
    user2.refresh_item().item.get('followerCount', 0) == 1

    # postprocess the delete and verify final state
    old_item = new_item
    new_item = None
    assert old_item['followStatus']['S'] == follow_status
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    user1.refresh_item().item.get('followedCount', 0) == 0
    user2.refresh_item().item.get('followerCount', 0) == 0

    # postprocess failed decrement, verify fails softly
    with caplog.at_level(logging.WARNING):
        follow_manager.postprocess_record(pk, sk, old_item, new_item)
    assert len(caplog.records) == 2
    assert all('Failed to decrement' in rec.msg for rec in caplog.records)
    assert sum('followerCount' in rec.msg for rec in caplog.records) == 1
    assert sum('followedCount' in rec.msg for rec in caplog.records) == 1
    assert sum(user1.id in rec.msg for rec in caplog.records) == 1
    assert sum(user2.id in rec.msg for rec in caplog.records) == 1
    user1.refresh_item().item.get('followedCount', 0) == 0
    user2.refresh_item().item.get('followerCount', 0) == 0


@pytest.mark.parametrize('follow_status', [s for s in FollowStatus._ALL if s != FollowStatus.FOLLOWING])
def test_postprocess_delete_no_change(follow_manager, user1, user2, follow_deets, follow_status):
    # set up and verify starting state
    item, typed_pk, pk, sk = follow_deets
    follow_manager.dynamo.update_following_status(item, follow_status)
    old_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
    new_item = None
    assert old_item['followStatus']['S'] == follow_status
    user1.refresh_item().item.get('followedCount', 0) == 0
    user2.refresh_item().item.get('followerCount', 0) == 0

    # postprocess the delete and verify final state
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    user1.refresh_item().item.get('followedCount', 0) == 0
    user2.refresh_item().item.get('followerCount', 0) == 0
