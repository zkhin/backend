from uuid import uuid4

import pendulum
import pytest

from app.models.follow.enums import FollowStatus
from app.models.post.enums import PostType
from app.models.user.enums import UserPrivacyStatus


@pytest.fixture
def users(user_manager):
    "Us and them"
    our_user = user_manager.create_cognito_only_user(str(uuid4()), 'myUsername')
    their_user = user_manager.create_cognito_only_user(str(uuid4()), 'theirUsername')
    yield (our_user, their_user)


@pytest.fixture
def their_post(follow_manager, users, post_manager):
    "Give them a completed post with an expiration in the next 24 hours"
    post = post_manager.add_post(
        users[1].id, str(uuid4()), PostType.TEXT_ONLY, lifetime_duration=pendulum.duration(hours=12), text='t',
    )
    yield post


@pytest.fixture
def users_private(follow_manager, users):
    "Us and them, they are private"
    our_user, their_user = users
    their_user.set_privacy_status(UserPrivacyStatus.PRIVATE)
    yield (our_user, their_user)


def test_get_follow_status(follow_manager, users):
    our_user, their_user = users
    assert follow_manager.get_follow_status(our_user.id, our_user.id) == 'SELF'
    assert follow_manager.get_follow_status(our_user.id, their_user.id) == 'NOT_FOLLOWING'

    # we follow them, then unfollow them
    follow_manager.request_to_follow(our_user, their_user)
    assert follow_manager.get_follow_status(our_user.id, their_user.id) == 'FOLLOWING'
    follow_manager.get_follow(our_user.id, their_user.id).unfollow()
    assert follow_manager.get_follow_status(our_user.id, their_user.id) == 'NOT_FOLLOWING'

    # we go private
    our_user.set_privacy_status(UserPrivacyStatus.PRIVATE)

    # they go through the follow request process, checking follow status along the way
    assert follow_manager.get_follow_status(their_user.id, our_user.id) == 'NOT_FOLLOWING'
    follow_manager.request_to_follow(their_user, our_user)
    assert follow_manager.get_follow_status(their_user.id, our_user.id) == 'REQUESTED'
    follow_manager.get_follow(their_user.id, our_user.id).deny()
    assert follow_manager.get_follow_status(their_user.id, our_user.id) == 'DENIED'
    follow_manager.get_follow(their_user.id, our_user.id).accept()
    assert follow_manager.get_follow_status(their_user.id, our_user.id) == 'FOLLOWING'
    follow_manager.get_follow(their_user.id, our_user.id).unfollow()
    assert follow_manager.get_follow_status(their_user.id, our_user.id) == 'NOT_FOLLOWING'


def test_request_to_follow_public_user(follow_manager, users):
    our_user, their_user = users

    # check we're not following them
    assert follow_manager.get_follow(our_user.id, their_user.id) is None

    # follow them, double check
    assert follow_manager.request_to_follow(our_user, their_user).status == FollowStatus.FOLLOWING
    assert follow_manager.get_follow(our_user.id, their_user.id).status == FollowStatus.FOLLOWING

    # check follow counters
    our_user.refresh_item()
    assert our_user.item.get('followerCount', 0) == 0
    assert our_user.item.get('followedCount', 0) == 1

    their_user.refresh_item()
    assert their_user.item.get('followerCount', 0) == 1
    assert their_user.item.get('followedCount', 0) == 0

    # check our feed
    our_feed_by_them = list(follow_manager.feed_manager.dynamo.generate_feed(our_user.id))
    assert len(our_feed_by_them) == 0

    # check the followedFirstStory
    follow = follow_manager.get_follow(our_user.id, their_user.id)
    pk = {
        'partitionKey': follow.item['partitionKey'].replace('following/', 'followedFirstStory/'),
        'sortKey': follow.item['sortKey'],
    }
    ffs = follow_manager.dynamo.client.get_item(pk)
    assert ffs is None


def test_request_to_follow_public_user_with_story(follow_manager, users, their_post):
    our_user, their_user = users

    # follow them, double check
    assert follow_manager.request_to_follow(our_user, their_user).status == FollowStatus.FOLLOWING
    assert follow_manager.get_follow(our_user.id, their_user.id).status == FollowStatus.FOLLOWING

    # check our feed
    our_feed_by_them = list(follow_manager.feed_manager.dynamo.generate_feed(our_user.id))
    assert len(our_feed_by_them) == 1
    assert our_feed_by_them[0]['postId'] == their_post.id

    # check the followedFirstStory
    follow = follow_manager.get_follow(our_user.id, their_user.id)
    pk = {
        'partitionKey': follow.item['partitionKey'].replace('following/', 'followedFirstStory/'),
        'sortKey': follow.item['sortKey'],
    }
    ffs = follow_manager.dynamo.client.get_item(pk)
    assert ffs['postId'] == their_post.id


def test_request_to_follow_private_user(follow_manager, users):
    our_user, their_user = users

    # set them to private
    their_user.set_privacy_status(UserPrivacyStatus.PRIVATE)

    # request to follow them, double check
    assert follow_manager.request_to_follow(our_user, their_user).status == FollowStatus.REQUESTED
    assert follow_manager.get_follow(our_user.id, their_user.id).status == FollowStatus.REQUESTED

    # check follow counters
    our_user.refresh_item()
    assert our_user.item.get('followerCount', 0) == 0
    assert our_user.item.get('followedCount', 0) == 0

    their_user.refresh_item()
    assert their_user.item.get('followerCount', 0) == 0
    assert their_user.item.get('followedCount', 0) == 0

    # check our feed
    our_feed_by_them = list(follow_manager.feed_manager.dynamo.generate_feed(our_user.id))
    assert len(our_feed_by_them) == 0

    # check the followedFirstStory
    follow = follow_manager.get_follow(our_user.id, their_user.id)
    pk = {
        'partitionKey': follow.item['partitionKey'].replace('following/', 'followedFirstStory/'),
        'sortKey': follow.item['sortKey'],
    }
    ffs = follow_manager.dynamo.client.get_item(pk)
    assert ffs is None


def test_request_to_follow_double_follow(follow_manager, users):
    our_user, their_user = users

    # follow them
    assert follow_manager.request_to_follow(our_user, their_user).status == FollowStatus.FOLLOWING

    # try to follow them again
    with pytest.raises(follow_manager.exceptions.AlreadyFollowing):
        follow_manager.request_to_follow(our_user, their_user)


def test_request_to_follow_blocker_blocked_user(follow_manager, users, block_manager):
    our_user, their_user = users

    # they block us
    block_item = block_manager.block(their_user, our_user)
    assert block_item['blockerUserId'] == their_user.id
    assert block_item['blockedUserId'] == our_user.id

    # verify we can't follow them
    with pytest.raises(follow_manager.exceptions.FollowException, match='block'):
        follow_manager.request_to_follow(our_user, their_user)

    # verify they can't follow us
    with pytest.raises(follow_manager.exceptions.FollowException, match='block'):
        follow_manager.request_to_follow(their_user, our_user)


def test_accept_all_requested_follow_requests(follow_manager, users_private):
    our_user, their_user = users_private

    # request to follow them
    assert follow_manager.request_to_follow(our_user, their_user).status == FollowStatus.REQUESTED

    # accept all REQUESTED the follow request
    follow_manager.accept_all_requested_follow_requests(their_user.id)
    assert follow_manager.get_follow(our_user.id, their_user.id).status == FollowStatus.FOLLOWING

    # nothing should change if we do it again
    follow_manager.accept_all_requested_follow_requests(their_user.id)
    assert follow_manager.get_follow(our_user.id, their_user.id).status == FollowStatus.FOLLOWING

    # deny the follow request
    assert follow_manager.get_follow(our_user.id, their_user.id).deny().status == FollowStatus.DENIED

    # nothing should change if we do it again
    follow_manager.accept_all_requested_follow_requests(their_user.id)
    assert follow_manager.get_follow(our_user.id, their_user.id).status == FollowStatus.DENIED


def test_delete_all_denied_follow_requests(follow_manager, users_private):
    our_user, their_user = users_private

    # request to follow them
    assert follow_manager.request_to_follow(our_user, their_user).status == FollowStatus.REQUESTED

    # delete all the denied follow requests, should not affect
    follow_manager.delete_all_denied_follow_requests(their_user.id)
    assert follow_manager.get_follow(our_user.id, their_user.id).status == FollowStatus.REQUESTED

    # deny the follow request
    assert follow_manager.get_follow(our_user.id, their_user.id).deny().status == FollowStatus.DENIED

    # delete all the denied follow requests, should disappear
    follow_manager.delete_all_denied_follow_requests(their_user.id)
    assert follow_manager.get_follow(our_user.id, their_user.id) is None


def test_reset_follower_items(follow_manager, users_private):
    our_user, their_user = users_private

    # request to follow them
    assert follow_manager.request_to_follow(our_user, their_user).status == FollowStatus.REQUESTED

    # do a reset, should clear
    follow_manager.reset_follower_items(their_user.id)
    assert follow_manager.get_follow(our_user.id, their_user.id) is None

    # request to follow, and accept the following
    assert follow_manager.request_to_follow(our_user, their_user).accept().status == FollowStatus.FOLLOWING

    # check counts
    assert our_user.refresh_item().item.get('followedCount', 0) == 1
    assert their_user.refresh_item().item.get('followerCount', 0) == 1

    # do reset, should clear and reset counts
    follow_manager.reset_follower_items(their_user.id)
    assert follow_manager.get_follow(our_user.id, their_user.id) is None

    # check counts
    assert our_user.refresh_item().item.get('followedCount', 0) == 0
    assert their_user.refresh_item().item.get('followerCount', 0) == 0


def test_reset_followed_items(follow_manager, users_private):
    our_user, their_user = users_private

    # request to follow them
    assert follow_manager.request_to_follow(our_user, their_user).status == FollowStatus.REQUESTED

    # do a reset, should clear
    follow_manager.reset_followed_items(our_user.id)
    assert follow_manager.get_follow(our_user.id, their_user.id) is None

    # request to follow, and accept the following
    assert follow_manager.request_to_follow(our_user, their_user).accept().status == FollowStatus.FOLLOWING

    # check counts
    assert our_user.refresh_item().item.get('followedCount', 0) == 1
    assert their_user.refresh_item().item.get('followerCount', 0) == 1

    # do reset, should clear and reset counts
    follow_manager.reset_followed_items(our_user.id)
    assert follow_manager.get_follow(our_user.id, their_user.id) is None

    # check counts
    assert our_user.refresh_item().item.get('followedCount', 0) == 0
    assert their_user.refresh_item().item.get('followerCount', 0) == 0


def test_generate_follower_user_ids(follow_manager, users, user_manager):
    our_user, their_user = users
    other_user = user_manager.create_cognito_only_user(str(uuid4()), 'otherUsername')

    # check we have no followers
    uids = list(follow_manager.generate_follower_user_ids(our_user.id))
    assert len(uids) == 0

    # they follow us
    assert follow_manager.request_to_follow(their_user, our_user).status == FollowStatus.FOLLOWING

    # check we have one follower
    uids = list(follow_manager.generate_follower_user_ids(our_user.id))
    assert uids == [their_user.id]

    # other follows us
    assert follow_manager.request_to_follow(other_user, our_user).status == FollowStatus.FOLLOWING

    # check we have two followers
    uids = list(follow_manager.generate_follower_user_ids(our_user.id))
    assert sorted(uids) == sorted([their_user.id, other_user.id])


def test_generate_followed_user_ids(follow_manager, users, user_manager):
    our_user, their_user = users
    other_user = user_manager.create_cognito_only_user(str(uuid4()), 'otherUsername')

    # check we have no followeds
    uids = list(follow_manager.generate_followed_user_ids(our_user.id))
    assert len(uids) == 0

    # we follow them
    assert follow_manager.request_to_follow(our_user, their_user).status == FollowStatus.FOLLOWING

    # check we have one followed
    uids = list(follow_manager.generate_followed_user_ids(our_user.id))
    assert uids == [their_user.id]

    # we follow other
    assert follow_manager.request_to_follow(our_user, other_user).status == FollowStatus.FOLLOWING

    # check we have two followeds
    uids = list(follow_manager.generate_followed_user_ids(our_user.id))
    assert sorted(uids) == sorted([their_user.id, other_user.id])
