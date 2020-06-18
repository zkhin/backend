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
def follow_deets_new_pk(follow_manager, user1, user2):
    item = follow_manager.dynamo.add_following(user1.id, user2.id, 'placeholder')
    typed_pk = follow_manager.dynamo.new_typed_pk(user1.id, user2.id)
    yield (item, typed_pk, typed_pk['partitionKey']['S'], typed_pk['sortKey']['S'])


@pytest.fixture
def follow_deets_old_pk(follow_manager, user1, user2):
    item = follow_manager.dynamo.add_following(user1.id, user2.id, 'placeholder', use_old_pk=True)
    typed_pk = follow_manager.dynamo.old_typed_pk(user1.id, user2.id)
    yield (item, typed_pk, typed_pk['partitionKey']['S'], typed_pk['sortKey']['S'])


# all the expected state changes that increment the follower & followed counts
@pytest.mark.parametrize(
    'old_follow_status, new_follow_status',
    [
        [None, FollowStatus.FOLLOWING],
        [FollowStatus.REQUESTED, FollowStatus.FOLLOWING],
        [FollowStatus.DENIED, FollowStatus.FOLLOWING],
    ],
)
@pytest.mark.parametrize('follow_deets', pytest.lazy_fixture(['follow_deets_new_pk', 'follow_deets_old_pk']))
def test_postprocess_increments_follower_followed_counts(
    follow_manager, user1, user2, follow_deets, old_follow_status, new_follow_status
):
    item, typed_pk, pk, sk = follow_deets

    if old_follow_status:
        follow_manager.dynamo.update_following_status(item, old_follow_status)
        old_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
        assert old_item['followStatus']['S'] == old_follow_status
    else:
        old_item = None

    if new_follow_status:
        follow_manager.dynamo.update_following_status(item, new_follow_status)
        new_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
        assert new_item['followStatus']['S'] == new_follow_status
    else:
        new_item = None

    # check starting state, postprocess, check final state, repeat
    assert user1.refresh_item().item.get('followedCount', 0) == 0
    assert user2.refresh_item().item.get('followerCount', 0) == 0
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    assert user1.refresh_item().item.get('followedCount', 0) == 1
    assert user2.refresh_item().item.get('followerCount', 0) == 1
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
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
@pytest.mark.parametrize('follow_deets', pytest.lazy_fixture(['follow_deets_new_pk', 'follow_deets_old_pk']))
def test_postprocess_no_change_follower_followed_counts(
    follow_manager, user1, user2, follow_deets, old_follow_status, new_follow_status
):
    item, typed_pk, pk, sk = follow_deets

    if old_follow_status:
        follow_manager.dynamo.update_following_status(item, old_follow_status)
        old_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
        assert old_item['followStatus']['S'] == old_follow_status
    else:
        old_item = None

    if new_follow_status:
        follow_manager.dynamo.update_following_status(item, new_follow_status)
        new_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
        assert new_item['followStatus']['S'] == new_follow_status
    else:
        new_item = None

    # check starting state, postprocess, check final state, repeat
    assert user1.refresh_item().item.get('followedCount', 0) == 0
    assert user2.refresh_item().item.get('followerCount', 0) == 0
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    assert user1.refresh_item().item.get('followedCount', 0) == 0
    assert user2.refresh_item().item.get('followerCount', 0) == 0
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    assert user1.refresh_item().item.get('followedCount', 0) == 0
    assert user2.refresh_item().item.get('followerCount', 0) == 0


# all the expected state changes that decrement the follower & followed counts
@pytest.mark.parametrize(
    'old_follow_status, new_follow_status',
    [[FollowStatus.FOLLOWING, FollowStatus.DENIED], [FollowStatus.FOLLOWING, None]],
)
@pytest.mark.parametrize('follow_deets', pytest.lazy_fixture(['follow_deets_new_pk', 'follow_deets_old_pk']))
def test_postprocess_decrements_follower_followed_counts(
    follow_manager, user1, user2, follow_deets, old_follow_status, new_follow_status, caplog
):
    item, typed_pk, pk, sk = follow_deets

    # do an increment to get a count in db so we can decrement, check state
    old_item = None
    follow_manager.dynamo.update_following_status(item, FollowStatus.FOLLOWING)
    new_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    assert user1.refresh_item().item.get('followedCount', 0) == 1
    assert user2.refresh_item().item.get('followerCount', 0) == 1

    if old_follow_status:
        follow_manager.dynamo.update_following_status(item, old_follow_status)
        old_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
        assert old_item['followStatus']['S'] == old_follow_status
    else:
        old_item = None

    if new_follow_status:
        follow_manager.dynamo.update_following_status(item, new_follow_status)
        new_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
        assert new_item['followStatus']['S'] == new_follow_status
    else:
        new_item = None

    # check starting state, postprocess, check final state
    assert user1.refresh_item().item.get('followedCount', 0) == 1
    assert user2.refresh_item().item.get('followerCount', 0) == 1
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    assert user1.refresh_item().item.get('followedCount', 0) == 0
    assert user2.refresh_item().item.get('followerCount', 0) == 0

    # postprocess failed decrement, verify fails softly
    with caplog.at_level(logging.WARNING):
        follow_manager.postprocess_record(pk, sk, old_item, new_item)
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
@pytest.mark.parametrize('follow_deets', pytest.lazy_fixture(['follow_deets_new_pk', 'follow_deets_old_pk']))
def test_postprocess_increments_requested_follower_count(
    follow_manager, user1, user2, follow_deets, old_follow_status, new_follow_status
):
    item, typed_pk, pk, sk = follow_deets

    if old_follow_status:
        follow_manager.dynamo.update_following_status(item, old_follow_status)
        old_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
        assert old_item['followStatus']['S'] == old_follow_status
    else:
        old_item = None

    if new_follow_status:
        follow_manager.dynamo.update_following_status(item, new_follow_status)
        new_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
        assert new_item['followStatus']['S'] == new_follow_status
    else:
        new_item = None

    # check starting state, postprocess, check final state, repeat
    assert user2.refresh_item().item.get('requestedFollowerCount', 0) == 0
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    assert user2.refresh_item().item.get('requestedFollowerCount', 0) == 1
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    assert user2.refresh_item().item.get('requestedFollowerCount', 0) == 2


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
@pytest.mark.parametrize('follow_deets', pytest.lazy_fixture(['follow_deets_new_pk', 'follow_deets_old_pk']))
def test_postprocess_no_change_requested_follower_count(
    follow_manager, user1, user2, follow_deets, old_follow_status, new_follow_status
):
    item, typed_pk, pk, sk = follow_deets

    if old_follow_status:
        follow_manager.dynamo.update_following_status(item, old_follow_status)
        old_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
        assert old_item['followStatus']['S'] == old_follow_status
    else:
        old_item = None

    if new_follow_status:
        follow_manager.dynamo.update_following_status(item, new_follow_status)
        new_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
        assert new_item['followStatus']['S'] == new_follow_status
    else:
        new_item = None

    # check starting state, postprocess, check final state, repeat
    assert user2.refresh_item().item.get('requestedFollowerCount', 0) == 0
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    assert user2.refresh_item().item.get('requestedFollowerCount', 0) == 0
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    assert user2.refresh_item().item.get('requestedFollowerCount', 0) == 0


# all the expected state changes that decrement the requested follower count
@pytest.mark.parametrize(
    'old_follow_status, new_follow_status',
    [
        [FollowStatus.REQUESTED, FollowStatus.FOLLOWING],
        [FollowStatus.REQUESTED, FollowStatus.DENIED],
        [FollowStatus.REQUESTED, None],
    ],
)
@pytest.mark.parametrize('follow_deets', pytest.lazy_fixture(['follow_deets_new_pk', 'follow_deets_old_pk']))
def test_postprocess_decrements_requested_follower_count(
    follow_manager, user1, user2, follow_deets, old_follow_status, new_follow_status, caplog
):
    item, typed_pk, pk, sk = follow_deets

    # do an increment to get a count in db so we can decrement, check state
    old_item = None
    follow_manager.dynamo.update_following_status(item, FollowStatus.REQUESTED)
    new_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    assert user2.refresh_item().item.get('requestedFollowerCount', 0) == 1

    if old_follow_status:
        follow_manager.dynamo.update_following_status(item, old_follow_status)
        old_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
        assert old_item['followStatus']['S'] == old_follow_status
    else:
        old_item = None

    if new_follow_status:
        follow_manager.dynamo.update_following_status(item, new_follow_status)
        new_item = follow_manager.dynamo.client.get_typed_item(typed_pk)
        assert new_item['followStatus']['S'] == new_follow_status
    else:
        new_item = None

    # check starting state, postprocess, check final state
    assert user2.refresh_item().item.get('requestedFollowerCount', 0) == 1
    follow_manager.postprocess_record(pk, sk, old_item, new_item)
    assert user2.refresh_item().item.get('requestedFollowerCount', 0) == 0

    # postprocess failed decrement, verify fails softly
    with caplog.at_level(logging.WARNING):
        follow_manager.postprocess_record(pk, sk, old_item, new_item)
    records = [rec for rec in caplog.records if 'requestedFollowerCount' in rec.msg]
    assert len(records) == 1
    assert all(x in records[0].msg for x in ('Failed to decrement', user2.id))
    assert user2.refresh_item().item.get('requestedFollowerCount', 0) == 0
