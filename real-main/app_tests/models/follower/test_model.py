import uuid

import pendulum
import pytest

from app.models.follower.enums import FollowStatus
from app.models.like.enums import LikeStatus
from app.models.post.enums import PostType
from app.models.user.enums import UserPrivacyStatus


@pytest.fixture
def users(user_manager, cognito_client):
    "Us and them"
    our_user_id, our_username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    their_user_id, their_username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(our_user_id, our_username, f'{our_username}@real.app')
    cognito_client.create_verified_user_pool_entry(their_user_id, their_username, f'{their_username}@real.app')
    our_user = user_manager.create_cognito_only_user(our_user_id, our_username)
    their_user = user_manager.create_cognito_only_user(their_user_id, their_username)
    yield (our_user, their_user)


@pytest.fixture
def their_post(follower_manager, users, post_manager):
    "Give them a completed post with an expiration in the next 24 hours"
    post = post_manager.add_post(
        users[1], str(uuid.uuid4()), PostType.TEXT_ONLY, lifetime_duration=pendulum.duration(hours=12), text='t',
    )
    yield post


@pytest.fixture
def follow(follower_manager, users):
    our_user, their_user = users
    follower_manager.request_to_follow(our_user, their_user)
    yield follower_manager.get_follow(our_user.id, their_user.id)


@pytest.fixture
def users_private(follower_manager, users):
    "Us and them, they are private"
    our_user, their_user = users
    their_user.set_privacy_status(UserPrivacyStatus.PRIVATE)
    yield (our_user, their_user)


@pytest.fixture
def requested_follow(follower_manager, users_private):
    our_user, their_user = users_private
    follower_manager.request_to_follow(our_user, their_user)
    yield follower_manager.get_follow(our_user.id, their_user.id)


def test_accept(users_private, requested_follow):
    follow = requested_follow
    assert follow.status == FollowStatus.REQUESTED

    # accept the follow request, double check
    assert follow.accept().status == FollowStatus.FOLLOWING
    assert follow.refresh_item().status == FollowStatus.FOLLOWING

    # verify we can't double accept
    with pytest.raises(follow.exceptions.FollowerAlreadyHasStatus):
        follow.accept()


def test_accept_follow_request_with_story(users_private, their_post, requested_follow, feed_manager):
    our_user, _ = users_private
    follow = requested_follow
    assert follow.status == FollowStatus.REQUESTED

    # accept the follow request, double check
    assert follow.accept().status == FollowStatus.FOLLOWING
    assert follow.refresh_item().status == FollowStatus.FOLLOWING

    # check our feed
    our_feed_by_them = list(feed_manager.dynamo.generate_feed(our_user.id))
    assert len(our_feed_by_them) == 1
    assert our_feed_by_them[0]['postId'] == their_post.id

    # check the followedFirstStory
    follower_user_id, followed_user_id = follow.item['followerUserId'], follow.item['followedUserId']
    pk = {
        'partitionKey': f'followedFirstStory/{follower_user_id}/{followed_user_id}',
        'sortKey': '-',
    }
    ffs = follow.dynamo.client.get_item(pk)
    assert ffs['postId'] == their_post.id


def test_deny_follow_request(users_private, requested_follow):
    our_user, their_user = users_private
    follow = requested_follow
    assert follow.status == FollowStatus.REQUESTED

    # deny the follow request, double check
    assert follow.deny().status == FollowStatus.DENIED
    assert follow.refresh_item().status == FollowStatus.DENIED

    # check follow counters
    our_user.refresh_item()
    assert our_user.item.get('followerCount', 0) == 0
    assert our_user.item.get('followedCount', 0) == 0

    their_user.refresh_item()
    assert their_user.item.get('followerCount', 0) == 0
    assert their_user.item.get('followedCount', 0) == 0

    # vierfy they can't deny our follow request again
    with pytest.raises(follow.exceptions.FollowerAlreadyHasStatus):
        follow.deny()


def test_deny_follow_request_that_was_previously_approved(users_private, requested_follow):
    our_user, their_user = users_private
    follow = requested_follow
    assert follow.status == FollowStatus.REQUESTED

    # approve the follow request
    assert follow.accept().status == FollowStatus.FOLLOWING

    # they change their mind and now deny us, double check
    assert follow.deny().status == FollowStatus.DENIED
    assert follow.refresh_item().status == FollowStatus.DENIED

    # check follow counters
    our_user.refresh_item()
    assert our_user.item.get('followerCount', 0) == 0
    assert our_user.item.get('followedCount', 0) == 0

    their_user.refresh_item()
    assert their_user.item.get('followerCount', 0) == 0
    assert their_user.item.get('followedCount', 0) == 0


def test_deny_follow_request_user_had_liked_post(users_private, their_post, requested_follow, like_manager):
    our_user, _ = users_private
    follow = requested_follow
    assert follow.status == FollowStatus.REQUESTED

    # approve the follow request
    assert follow.accept().status == FollowStatus.FOLLOWING

    # we like their post
    like_manager.like_post(our_user, their_post, LikeStatus.ONYMOUSLY_LIKED)
    like = like_manager.get_like(our_user.id, their_post.id)
    assert like.item['likeStatus'] == LikeStatus.ONYMOUSLY_LIKED

    # they change their mind and deny our following
    assert follow.deny().status == FollowStatus.DENIED

    # check the like was removed from their post
    assert like_manager.get_like(our_user.id, their_post.id) is None


def test_unfollow_public_user_we_were_following(users, follow):
    our_user, their_user = users
    assert follow.status == FollowStatus.FOLLOWING

    # unfollow them, double check
    assert follow.unfollow().status == FollowStatus.NOT_FOLLOWING
    assert follow.refresh_item().status == FollowStatus.NOT_FOLLOWING

    # check follow counters
    our_user.refresh_item()
    assert our_user.item.get('followerCount', 0) == 0
    assert our_user.item.get('followedCount', 0) == 0

    their_user.refresh_item()
    assert their_user.item.get('followerCount', 0) == 0
    assert their_user.item.get('followedCount', 0) == 0


def test_unfollow_private_user_we_had_requested_to_follow(users_private, requested_follow):
    follow = requested_follow
    assert follow.status == FollowStatus.REQUESTED

    # unfollow them, double check
    assert follow.unfollow().status == FollowStatus.NOT_FOLLOWING
    assert follow.refresh_item().status == FollowStatus.NOT_FOLLOWING


def test_unfollow_private_user_we_were_following(users_private, their_post, requested_follow, like_manager):
    our_user, _ = users_private
    follow = requested_follow
    assert follow.status == FollowStatus.REQUESTED

    # approve the follow request
    assert follow.accept().status == FollowStatus.FOLLOWING

    # like their post
    like_manager.like_post(our_user, their_post, LikeStatus.ONYMOUSLY_LIKED)
    like = like_manager.get_like(our_user.id, their_post.id)
    assert like.item['likeStatus'] == LikeStatus.ONYMOUSLY_LIKED

    # unfollow them
    assert follow.unfollow().status == FollowStatus.NOT_FOLLOWING
    assert follow.refresh_item().status == FollowStatus.NOT_FOLLOWING

    # check the like was removed from their post
    assert like_manager.get_like(our_user.id, their_post.id) is None
