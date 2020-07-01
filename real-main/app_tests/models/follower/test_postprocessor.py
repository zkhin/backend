import logging
from uuid import uuid4

import pytest

from app.models.follower.enums import FollowStatus


@pytest.fixture
def follower_postprocessor(follower_manager):
    yield follower_manager.postprocessor


@pytest.fixture
def user1(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user1


@pytest.fixture
def follower_item(follower_manager, user1, user2):
    yield follower_manager.dynamo.add_following(user1.id, user2.id, 'placeholder')


# all the expected state changes that increment the follower & followed counts
@pytest.mark.parametrize(
    'old_follow_status, new_follow_status',
    [
        [None, FollowStatus.FOLLOWING],
        [FollowStatus.REQUESTED, FollowStatus.FOLLOWING],
        [FollowStatus.DENIED, FollowStatus.FOLLOWING],
    ],
)
def test_run_increments_follower_followed_counts(
    follower_postprocessor, follower_manager, user1, user2, follower_item, old_follow_status, new_follow_status
):
    pk, sk = follower_item['partitionKey'], follower_item['sortKey']

    if old_follow_status:
        old_item = follower_manager.dynamo.update_following_status(follower_item, old_follow_status)
        assert old_item['followStatus'] == old_follow_status
    else:
        old_item = None

    if new_follow_status:
        new_item = follower_manager.dynamo.update_following_status(follower_item, new_follow_status)
        assert new_item['followStatus'] == new_follow_status
    else:
        new_item = None

    # check starting state, postprocess, check final state, repeat
    assert user1.refresh_item().item.get('followedCount', 0) == 0
    assert user2.refresh_item().item.get('followerCount', 0) == 0
    follower_postprocessor.run(pk, sk, old_item, new_item)
    assert user1.refresh_item().item.get('followedCount', 0) == 1
    assert user2.refresh_item().item.get('followerCount', 0) == 1
    follower_postprocessor.run(pk, sk, old_item, new_item)
    assert user1.refresh_item().item.get('followedCount', 0) == 2
    assert user2.refresh_item().item.get('followerCount', 0) == 2


# all the expected state changes that don't change the follower & followed counts
@pytest.mark.parametrize(
    'old_follow_status, new_follow_status',
    [
        [None, FollowStatus.REQUESTED],
        [FollowStatus.REQUESTED, FollowStatus.DENIED],
        [FollowStatus.REQUESTED, None],
        [FollowStatus.DENIED, None],
    ],
)
def test_run_no_change_follower_followed_counts(
    follower_postprocessor, follower_manager, user1, user2, follower_item, old_follow_status, new_follow_status
):
    pk, sk = follower_item['partitionKey'], follower_item['sortKey']

    if old_follow_status:
        old_item = follower_manager.dynamo.update_following_status(follower_item, old_follow_status)
        assert old_item['followStatus'] == old_follow_status
    else:
        old_item = None

    if new_follow_status:
        new_item = follower_manager.dynamo.update_following_status(follower_item, new_follow_status)
        assert new_item['followStatus'] == new_follow_status
    else:
        new_item = None

    # check starting state, postprocess, check final state, repeat
    assert user1.refresh_item().item.get('followedCount', 0) == 0
    assert user2.refresh_item().item.get('followerCount', 0) == 0
    follower_postprocessor.run(pk, sk, old_item, new_item)
    assert user1.refresh_item().item.get('followedCount', 0) == 0
    assert user2.refresh_item().item.get('followerCount', 0) == 0
    follower_postprocessor.run(pk, sk, old_item, new_item)
    assert user1.refresh_item().item.get('followedCount', 0) == 0
    assert user2.refresh_item().item.get('followerCount', 0) == 0


# all the expected state changes that decrement the follower & followed counts
@pytest.mark.parametrize(
    'old_follow_status, new_follow_status',
    [[FollowStatus.FOLLOWING, FollowStatus.DENIED], [FollowStatus.FOLLOWING, None]],
)
def test_run_decrements_follower_followed_counts(
    follower_postprocessor,
    follower_manager,
    user1,
    user2,
    follower_item,
    old_follow_status,
    new_follow_status,
    caplog,
):
    pk, sk = follower_item['partitionKey'], follower_item['sortKey']

    # do an increment to get a count in db so we can decrement, check state
    old_item = None
    new_item = follower_manager.dynamo.update_following_status(follower_item, FollowStatus.FOLLOWING)
    follower_postprocessor.run(pk, sk, old_item, new_item)
    assert user1.refresh_item().item.get('followedCount', 0) == 1
    assert user2.refresh_item().item.get('followerCount', 0) == 1

    if old_follow_status:
        old_item = follower_manager.dynamo.update_following_status(follower_item, old_follow_status)
        assert old_item['followStatus'] == old_follow_status
    else:
        old_item = None

    if new_follow_status:
        new_item = follower_manager.dynamo.update_following_status(follower_item, new_follow_status)
        assert new_item['followStatus'] == new_follow_status
    else:
        new_item = None

    # check starting state, postprocess, check final state
    assert user1.refresh_item().item.get('followedCount', 0) == 1
    assert user2.refresh_item().item.get('followerCount', 0) == 1
    follower_postprocessor.run(pk, sk, old_item, new_item)
    assert user1.refresh_item().item.get('followedCount', 0) == 0
    assert user2.refresh_item().item.get('followerCount', 0) == 0

    # postprocess failed decrement, verify fails softly
    with caplog.at_level(logging.WARNING):
        follower_postprocessor.run(pk, sk, old_item, new_item)
    follower_records = [rec for rec in caplog.records if 'followerCount' in rec.msg]
    followed_records = [rec for rec in caplog.records if 'followedCount' in rec.msg]
    assert len(follower_records) == 1
    assert len(followed_records) == 1
    assert all(x in followed_records[0].msg for x in ('Failed to decrement', user1.id))
    assert all(x in follower_records[0].msg for x in ('Failed to decrement', user2.id))
    assert user1.refresh_item().item.get('followedCount', 0) == 0
    assert user2.refresh_item().item.get('followerCount', 0) == 0


# all the expected state changes that increment the requested follower count
@pytest.mark.parametrize(
    'old_follow_status, new_follow_status', [[None, FollowStatus.REQUESTED]],
)
def test_run_increments_followers_requested_count(
    follower_postprocessor, follower_manager, user1, user2, follower_item, old_follow_status, new_follow_status
):
    pk, sk = follower_item['partitionKey'], follower_item['sortKey']

    if old_follow_status:
        old_item = follower_manager.dynamo.update_following_status(follower_item, old_follow_status)
        assert old_item['followStatus'] == old_follow_status
    else:
        old_item = None

    if new_follow_status:
        new_item = follower_manager.dynamo.update_following_status(follower_item, new_follow_status)
        assert new_item['followStatus'] == new_follow_status
    else:
        new_item = None

    # check starting state, postprocess, check final state, repeat
    assert user2.refresh_item().item.get('followersRequestedCount', 0) == 0
    follower_postprocessor.run(pk, sk, old_item, new_item)
    assert user2.refresh_item().item.get('followersRequestedCount', 0) == 1
    follower_postprocessor.run(pk, sk, old_item, new_item)
    assert user2.refresh_item().item.get('followersRequestedCount', 0) == 2


# all the expected state changes that don't change the requested follower count
@pytest.mark.parametrize(
    'old_follow_status, new_follow_status',
    [
        [None, FollowStatus.FOLLOWING],
        [FollowStatus.FOLLOWING, FollowStatus.DENIED],
        [FollowStatus.FOLLOWING, None],
        [FollowStatus.DENIED, FollowStatus.FOLLOWING],
        [FollowStatus.DENIED, None],
    ],
)
def test_run_no_change_followers_requested_count(
    follower_postprocessor, follower_manager, user1, user2, follower_item, old_follow_status, new_follow_status
):
    pk, sk = follower_item['partitionKey'], follower_item['sortKey']

    if old_follow_status:
        old_item = follower_manager.dynamo.update_following_status(follower_item, old_follow_status)
        assert old_item['followStatus'] == old_follow_status
    else:
        old_item = None

    if new_follow_status:
        new_item = follower_manager.dynamo.update_following_status(follower_item, new_follow_status)
        assert new_item['followStatus'] == new_follow_status
    else:
        new_item = None

    # check starting state, postprocess, check final state, repeat
    assert user2.refresh_item().item.get('followersRequestedCount', 0) == 0
    follower_postprocessor.run(pk, sk, old_item, new_item)
    assert user2.refresh_item().item.get('followersRequestedCount', 0) == 0
    follower_postprocessor.run(pk, sk, old_item, new_item)
    assert user2.refresh_item().item.get('followersRequestedCount', 0) == 0


# all the expected state changes that decrement the requested follower count
@pytest.mark.parametrize(
    'old_follow_status, new_follow_status',
    [
        [FollowStatus.REQUESTED, FollowStatus.FOLLOWING],
        [FollowStatus.REQUESTED, FollowStatus.DENIED],
        [FollowStatus.REQUESTED, None],
    ],
)
def test_run_decrements_followers_requested_count(
    follower_postprocessor,
    follower_manager,
    user1,
    user2,
    follower_item,
    old_follow_status,
    new_follow_status,
    caplog,
):
    pk, sk = follower_item['partitionKey'], follower_item['sortKey']

    # do an increment to get a count in db so we can decrement, check state
    old_item = None
    new_item = follower_manager.dynamo.update_following_status(follower_item, FollowStatus.REQUESTED)
    follower_postprocessor.run(pk, sk, old_item, new_item)
    assert user2.refresh_item().item.get('followersRequestedCount', 0) == 1

    if old_follow_status:
        old_item = follower_manager.dynamo.update_following_status(follower_item, old_follow_status)
        assert old_item['followStatus'] == old_follow_status
    else:
        old_item = None

    if new_follow_status:
        new_item = follower_manager.dynamo.update_following_status(follower_item, new_follow_status)
        assert new_item['followStatus'] == new_follow_status
    else:
        new_item = None

    # check starting state, postprocess, check final state
    assert user2.refresh_item().item.get('followersRequestedCount', 0) == 1
    follower_postprocessor.run(pk, sk, old_item, new_item)
    assert user2.refresh_item().item.get('followersRequestedCount', 0) == 0

    # postprocess failed decrement, verify fails softly
    with caplog.at_level(logging.WARNING):
        follower_postprocessor.run(pk, sk, old_item, new_item)
    records = [rec for rec in caplog.records if 'followersRequestedCount' in rec.msg]
    assert len(records) == 1
    assert all(x in records[0].msg for x in ('Failed to decrement', user2.id))
    assert user2.refresh_item().item.get('followersRequestedCount', 0) == 0
