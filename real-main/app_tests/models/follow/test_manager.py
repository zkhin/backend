from uuid import uuid4

from isodate.duration import Duration
import pytest

from app.models.follow import FollowManager
from app.models.follow.enums import FollowStatus
from app.models.like.enums import LikeStatus
from app.models.post import PostManager
from app.models.user.enums import UserPrivacyStatus


@pytest.fixture
def post_manager(dynamo_client):
    yield PostManager({'dynamo': dynamo_client})


@pytest.fixture
def follow_manager(dynamo_client):
    yield FollowManager({'dynamo': dynamo_client})


@pytest.fixture
def users(user_manager):
    "Us and them"
    our_user = user_manager.create_cognito_only_user(str(uuid4()), 'myUsername')
    their_user = user_manager.create_cognito_only_user(str(uuid4()), 'theirUsername')
    yield (our_user, their_user)


@pytest.fixture
def their_post(follow_manager, users, post_manager):
    "Give them a completed post with an expiration in the next 24 hours"
    post = post_manager.add_post(users[1].id, str(uuid4()), lifetime_duration=Duration(hours=12), text='t')
    yield post


@pytest.fixture
def users_private(follow_manager, users):
    "Us and them, they are private"
    our_user, their_user = users
    their_user.set_privacy_status(UserPrivacyStatus.PRIVATE)
    yield (our_user, their_user)


def test_request_to_follow_public_user(follow_manager, users):
    our_user, their_user = users

    # check we're not following them
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following is None

    # follow them
    status = follow_manager.request_to_follow(our_user, their_user)
    assert status == FollowStatus.FOLLOWING

    # check we are following them
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.FOLLOWING

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
    pk = {
        'partitionKey': following['partitionKey'].replace('following/', 'followedFirstStory/'),
        'sortKey': following['sortKey'],
    }
    ffs = follow_manager.dynamo.client.get_item(pk)
    assert ffs is None


def test_request_to_follow_public_user_with_story(follow_manager, users, their_post):
    our_user, their_user = users

    # follow them
    status = follow_manager.request_to_follow(our_user, their_user)
    assert status == FollowStatus.FOLLOWING

    # check we are following them
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.FOLLOWING

    # check our feed
    our_feed_by_them = list(follow_manager.feed_manager.dynamo.generate_feed(our_user.id))
    assert len(our_feed_by_them) == 1
    assert our_feed_by_them[0]['postId'] == their_post.id

    # check the followedFirstStory
    pk = {
        'partitionKey': following['partitionKey'].replace('following/', 'followedFirstStory/'),
        'sortKey': following['sortKey'],
    }
    ffs = follow_manager.dynamo.client.get_item(pk)
    assert ffs['postId'] == their_post.id


def test_request_to_follow_private_user(follow_manager, users):
    our_user, their_user = users

    # set them to private
    their_user.set_privacy_status(UserPrivacyStatus.PRIVATE)

    # request to follow them
    status = follow_manager.request_to_follow(our_user, their_user)
    assert status == FollowStatus.REQUESTED

    # check we did request to follow
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.REQUESTED

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
    pk = {
        'partitionKey': following['partitionKey'].replace('following/', 'followedFirstStory/'),
        'sortKey': following['sortKey'],
    }
    ffs = follow_manager.dynamo.client.get_item(pk)
    assert ffs is None


def test_request_to_follow_double_follow(follow_manager, users):
    our_user, their_user = users

    # follow them
    status = follow_manager.request_to_follow(our_user, their_user)
    assert status == FollowStatus.FOLLOWING

    # try to follow them again
    with pytest.raises(follow_manager.exceptions.AlreadyFollowing):
        follow_manager.request_to_follow(our_user, their_user)


def test_accept_follow_request(follow_manager, users_private):
    our_user, their_user = users_private

    # request to follow them
    follow_manager.request_to_follow(our_user, their_user)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.REQUESTED

    # accept the follow request
    status = follow_manager.accept_follow_request(our_user.id, their_user.id)
    assert status == FollowStatus.FOLLOWING

    # check we really follow them
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.FOLLOWING

    # check follow counters
    our_user.refresh_item()
    assert our_user.item.get('followerCount', 0) == 0
    assert our_user.item.get('followedCount', 0) == 1

    their_user.refresh_item()
    assert their_user.item.get('followerCount', 0) == 1
    assert their_user.item.get('followedCount', 0) == 0


def test_accept_follow_request_with_story(follow_manager, users_private, their_post):
    our_user, their_user = users_private

    # request to follow them
    follow_manager.request_to_follow(our_user, their_user)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.REQUESTED

    # accept the follow request
    status = follow_manager.accept_follow_request(our_user.id, their_user.id)
    assert status == FollowStatus.FOLLOWING

    # check we really follow them
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.FOLLOWING

    # check our feed
    our_feed_by_them = list(follow_manager.feed_manager.dynamo.generate_feed(our_user.id))
    assert len(our_feed_by_them) == 1
    assert our_feed_by_them[0]['postId'] == their_post.id

    # check the followedFirstStory
    pk = {
        'partitionKey': following['partitionKey'].replace('following/', 'followedFirstStory/'),
        'sortKey': following['sortKey'],
    }
    ffs = follow_manager.dynamo.client.get_item(pk)
    assert ffs['postId'] == their_post.id


def test_accept_follow_request_already_accepted(follow_manager, users_private):
    our_user, their_user = users_private

    # request to follow them
    follow_manager.request_to_follow(our_user, their_user)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.REQUESTED

    # accept the follow request
    status = follow_manager.accept_follow_request(our_user.id, their_user.id)
    assert status == FollowStatus.FOLLOWING

    # try to accept it again
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    with pytest.raises(follow_manager.exceptions.AlreadyHasStatus):
        follow_manager.accept_follow_request(our_user.id, their_user.id)


def test_deny_follow_request(follow_manager, users_private):
    our_user, their_user = users_private

    # request to follow them
    follow_manager.request_to_follow(our_user, their_user)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.REQUESTED

    # deny the follow request
    status = follow_manager.deny_follow_request(our_user.id, their_user.id)
    assert status == FollowStatus.DENIED

    # check we really deny them
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.DENIED

    # check follow counters
    our_user.refresh_item()
    assert our_user.item.get('followerCount', 0) == 0
    assert our_user.item.get('followedCount', 0) == 0

    their_user.refresh_item()
    assert their_user.item.get('followerCount', 0) == 0
    assert their_user.item.get('followedCount', 0) == 0


def test_deny_follow_request_that_was_previously_approved(follow_manager, users_private):
    our_user, their_user = users_private

    # request to follow them
    follow_manager.request_to_follow(our_user, their_user)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.REQUESTED

    # approve the follow request
    status = follow_manager.accept_follow_request(our_user.id, their_user.id)
    assert status == FollowStatus.FOLLOWING

    # they change their mind and now deny us
    status = follow_manager.deny_follow_request(our_user.id, their_user.id)
    assert status == FollowStatus.DENIED

    # check we really deny them
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.DENIED

    # check follow counters
    our_user.refresh_item()
    assert our_user.item.get('followerCount', 0) == 0
    assert our_user.item.get('followedCount', 0) == 0

    their_user.refresh_item()
    assert their_user.item.get('followerCount', 0) == 0
    assert their_user.item.get('followedCount', 0) == 0


def test_deny_follow_request_user_had_liked_post(follow_manager, users_private, their_post):
    our_user, their_user = users_private

    # request to follow them
    follow_manager.request_to_follow(our_user, their_user)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.REQUESTED

    # they accept the follow request
    status = follow_manager.accept_follow_request(our_user.id, their_user.id)
    assert status == FollowStatus.FOLLOWING

    # we like their post
    follow_manager.like_manager.like_post(our_user, their_post, LikeStatus.ONYMOUSLY_LIKED)
    like = follow_manager.like_manager.get_like(our_user.id, their_post.id)
    assert like.item['likeStatus'] == LikeStatus.ONYMOUSLY_LIKED

    # they change their mind and deny our following
    status = follow_manager.deny_follow_request(our_user.id, their_user.id)
    assert status == FollowStatus.DENIED

    # check they really did deny us
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.DENIED

    # check the like was removed from their post
    assert follow_manager.like_manager.get_like(our_user.id, their_post.id) is None


def test_request_to_follow_deny_follow(follow_manager, users_private):
    our_user, their_user = users_private

    # request to follow them
    follow_manager.request_to_follow(our_user, their_user)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.REQUESTED

    # they deny our follow request
    status = follow_manager.deny_follow_request(our_user.id, their_user.id)
    assert status == FollowStatus.DENIED

    # they try to deny our follow request again
    with pytest.raises(follow_manager.exceptions.AlreadyHasStatus):
        follow_manager.deny_follow_request(our_user.id, their_user.id)


def test_unfollow_public_user_we_were_following(follow_manager, users):
    our_user, their_user = users

    # follow them
    follow_manager.request_to_follow(our_user, their_user)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.FOLLOWING

    # unfollow them
    status = follow_manager.unfollow(our_user.id, their_user.id)
    assert status == FollowStatus.NOT_FOLLOWING

    # check we really did unfollow them
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following is None

    # check follow counters
    our_user.refresh_item()
    assert our_user.item.get('followerCount', 0) == 0
    assert our_user.item.get('followedCount', 0) == 0

    their_user.refresh_item()
    assert their_user.item.get('followerCount', 0) == 0
    assert their_user.item.get('followedCount', 0) == 0


def test_unfollow_private_user_we_had_requested_to_follow(follow_manager, users):
    our_user, their_user = users

    # set them to private
    their_user.set_privacy_status(UserPrivacyStatus.PRIVATE)

    # request to follow them
    follow_manager.request_to_follow(our_user, their_user)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.REQUESTED

    # unfollow them
    status = follow_manager.unfollow(our_user.id, their_user.id)
    assert status == FollowStatus.NOT_FOLLOWING

    # check we really did unfollow them
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following is None


def test_unfollow_private_user_we_were_following(follow_manager, users, their_post):
    our_user, their_user = users

    # follow them
    follow_manager.request_to_follow(our_user, their_user)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.FOLLOWING

    # set them to private
    their_user.set_privacy_status(UserPrivacyStatus.PRIVATE)

    # like their post
    follow_manager.like_manager.like_post(our_user, their_post, LikeStatus.ONYMOUSLY_LIKED)
    like = follow_manager.like_manager.get_like(our_user.id, their_post.id)
    assert like.item['likeStatus'] == LikeStatus.ONYMOUSLY_LIKED

    # unfollow them
    status = follow_manager.unfollow(our_user.id, their_user.id)
    assert status == FollowStatus.NOT_FOLLOWING

    # check we really did unfollow them
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following is None

    # check the like was removed from their post
    assert follow_manager.like_manager.get_like(our_user.id, their_post.id) is None


def test_accept_all_requested_follow_requests(follow_manager, users_private):
    our_user, their_user = users_private

    # request to follow them
    follow_manager.request_to_follow(our_user, their_user)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.REQUESTED

    # accept all REQUESTED the follow request
    follow_manager.accept_all_requested_follow_requests(their_user.id)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.FOLLOWING

    # nothing should change if we do it again
    follow_manager.accept_all_requested_follow_requests(their_user.id)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.FOLLOWING

    # deny the follow request
    follow_manager.deny_follow_request(our_user.id, their_user.id)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.DENIED

    # nothing should change if we do it again
    follow_manager.accept_all_requested_follow_requests(their_user.id)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.DENIED


def test_delete_all_denied_follow_requests(follow_manager, users_private):
    our_user, their_user = users_private

    # request to follow them
    follow_manager.request_to_follow(our_user, their_user)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.REQUESTED

    # delete all the denied follow requests, should not affect
    follow_manager.delete_all_denied_follow_requests(their_user.id)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.REQUESTED

    # deny the follow request
    follow_manager.deny_follow_request(our_user.id, their_user.id)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.DENIED

    # delete all the denied follow requests, should disappear
    follow_manager.delete_all_denied_follow_requests(their_user.id)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following is None


def test_reset_follower_items(follow_manager, users_private):
    our_user, their_user = users_private

    # request to follow them
    follow_manager.request_to_follow(our_user, their_user)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.REQUESTED

    # do a reset, should clear
    follow_manager.reset_follower_items(their_user.id)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following is None

    # request to follow, and accept the following
    follow_manager.request_to_follow(our_user, their_user)
    follow_manager.accept_follow_request(our_user.id, their_user.id)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.FOLLOWING

    # check counts
    our_user.refresh_item()
    assert our_user.item.get('followedCount', 0) == 1
    their_user.refresh_item()
    assert their_user.item.get('followerCount', 0) == 1

    # do reset, should clear and reset counts
    follow_manager.reset_follower_items(their_user.id)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following is None

    # check counts
    our_user.refresh_item()
    assert our_user.item.get('followedCount', 0) == 0
    our_user.refresh_item()
    assert our_user.item.get('followerCount', 0) == 0


def test_reset_followed_items(follow_manager, users_private):
    our_user, their_user = users_private

    # request to follow them
    follow_manager.request_to_follow(our_user, their_user)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.REQUESTED

    # do a reset, should clear
    follow_manager.reset_followed_items(our_user.id)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following is None

    # request to follow, and accept the following
    follow_manager.request_to_follow(our_user, their_user)
    follow_manager.accept_follow_request(our_user.id, their_user.id)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.FOLLOWING

    # check counts
    our_user.refresh_item()
    assert our_user.item.get('followedCount', 0) == 1
    their_user.refresh_item()
    assert their_user.item.get('followerCount', 0) == 1

    # do reset, should clear and reset counts
    follow_manager.reset_followed_items(our_user.id)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following is None

    # check counts
    our_user.refresh_item()
    assert our_user.item.get('followedCount', 0) == 0
    our_user.refresh_item()
    assert our_user.item.get('followerCount', 0) == 0


def test_generate_follower_user_ids(follow_manager, users, user_manager):
    our_user, their_user = users
    other_user = user_manager.create_cognito_only_user(str(uuid4()), 'otherUsername')

    # check we have no followers
    uids = list(follow_manager.generate_follower_user_ids(our_user.id))
    assert len(uids) == 0

    # they follow us
    follow_manager.request_to_follow(their_user, our_user)
    following = follow_manager.dynamo.get_following(their_user.id, our_user.id)
    assert following['followStatus'] == FollowStatus.FOLLOWING

    # check we have one follower
    uids = list(follow_manager.generate_follower_user_ids(our_user.id))
    assert uids == [their_user.id]

    # other follows us
    follow_manager.request_to_follow(other_user, our_user)
    following = follow_manager.dynamo.get_following(other_user.id, our_user.id)
    assert following['followStatus'] == FollowStatus.FOLLOWING

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
    follow_manager.request_to_follow(our_user, their_user)
    following = follow_manager.dynamo.get_following(our_user.id, their_user.id)
    assert following['followStatus'] == FollowStatus.FOLLOWING

    # check we have one followed
    uids = list(follow_manager.generate_followed_user_ids(our_user.id))
    assert uids == [their_user.id]

    # we follow other
    follow_manager.request_to_follow(our_user, other_user)
    following = follow_manager.dynamo.get_following(our_user.id, other_user.id)
    assert following['followStatus'] == FollowStatus.FOLLOWING

    # check we have two followeds
    uids = list(follow_manager.generate_followed_user_ids(our_user.id))
    assert sorted(uids) == sorted([their_user.id, other_user.id])
