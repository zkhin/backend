import logging
from uuid import uuid4

import pendulum
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


@pytest.fixture
def follower_first_story_item(follower_manager):
    user_id1, user_id2 = str(uuid4()), str(uuid4())
    post_item = {
        'postedByUserId': user_id2,
        'postId': str(uuid4()),
        'expiresAt': pendulum.now('utc').to_iso8601_string(),
    }
    follower_manager.first_story_dynamo.set_all((uid for uid in [user_id1]), post_item)
    yield follower_manager.dynamo.client.get_item(
        {'partitionKey': f'user/{user_id2}', 'sortKey': f'follower/{user_id1}/firstStory'}
    )


def test_does_nothing_for_ffs_item(follower_postprocessor, follower_first_story_item, dynamo_client):
    item = follower_first_story_item
    pk, sk = item['partitionKey'], item['sortKey']
    # check starting state
    assert dynamo_client.table.scan()['Items'] == [item]

    # process an add, check nothing changed
    follower_postprocessor.run(pk, sk, None, item)
    assert dynamo_client.table.scan()['Items'] == [item]

    # process an edit, check nothing changed
    follower_postprocessor.run(pk, sk, item, item)
    assert dynamo_client.table.scan()['Items'] == [item]

    # delete item from DB, check state
    dynamo_client.table.delete_item(Key={'partitionKey': pk, 'sortKey': sk})
    assert dynamo_client.table.scan()['Items'] == []

    # process a delete, check nothing changed
    follower_postprocessor.run(pk, sk, item, None)
    assert dynamo_client.table.scan()['Items'] == []


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
