import logging

from app import models
from app.models.user.enums import UserPrivacyStatus

from . import enums, exceptions
from .dynamo import FollowDynamo
from .model import Follow

logger = logging.getLogger()


class FollowManager:

    enums = enums
    exceptions = exceptions

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['follow'] = self
        self.feed_manager = managers.get('feed') or models.FeedManager(clients, managers=managers)
        self.ffs_manager = managers.get('followed_first_story') or models.FollowedFirstStoryManager(
            clients, managers=managers
        )
        self.block_manager = managers.get('block') or models.BlockManager(clients, managers=managers)
        self.like_manager = managers.get('like') or models.LikeManager(clients, managers=managers)
        self.post_manager = managers.get('post') or models.PostManager(clients, managers=managers)
        self.user_manager = managers.get('user') or models.UserManager(clients, managers=managers)

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = FollowDynamo(clients['dynamo'])

    def get_follow(self, follower_user_id, followed_user_id, strongly_consistent=False):
        item = self.dynamo.get_following(follower_user_id, followed_user_id, strongly_consistent=strongly_consistent)
        return self.init_follow(item) if item else None

    def init_follow(self, follow_item):
        return Follow(
            follow_item,
            self.dynamo,
            ffs_manager=self.ffs_manager,
            feed_manager=self.feed_manager,
            like_manager=self.like_manager,
            post_manager=self.post_manager,
            user_manager=self.user_manager,
        )

    def postprocess_record(self, pk, sk, old_item, new_item):
        try:
            # old pk format
            _, follower_user_id, followed_user_id = pk.split('/')
        except ValueError:
            # new pk format
            followed_user_id = pk[len('user/') :]
            follower_user_id = sk[len('follower/') :]

        old_status = old_item['followStatus']['S'] if old_item else enums.FollowStatus.NOT_FOLLOWING
        new_status = new_item['followStatus']['S'] if new_item else enums.FollowStatus.NOT_FOLLOWING

        # incr/decr followedCount and followerCount if follow status changed to/from FOLLOWING and something else
        if old_status != enums.FollowStatus.FOLLOWING and new_status == enums.FollowStatus.FOLLOWING:
            self.user_manager.dynamo.increment_followed_count(follower_user_id)
            self.user_manager.dynamo.increment_follower_count(followed_user_id)
        if old_status == enums.FollowStatus.FOLLOWING and new_status != enums.FollowStatus.FOLLOWING:
            self.user_manager.dynamo.decrement_followed_count(follower_user_id, fail_soft=True)
            self.user_manager.dynamo.decrement_follower_count(followed_user_id, fail_soft=True)

        # incr/decr followersRequestedCount if follow status changed to/from REQUESTED and something else
        if old_status != enums.FollowStatus.REQUESTED and new_status == enums.FollowStatus.REQUESTED:
            self.user_manager.dynamo.increment_followers_requested_count(followed_user_id)
        if old_status == enums.FollowStatus.REQUESTED and new_status != enums.FollowStatus.REQUESTED:
            self.user_manager.dynamo.decrement_followers_requested_count(followed_user_id, fail_soft=True)

    def get_follow_status(self, follower_user_id, followed_user_id):
        if follower_user_id == followed_user_id:
            return enums.FollowStatus.SELF
        follow = self.get_follow(follower_user_id, followed_user_id)
        if not follow:
            return enums.FollowStatus.NOT_FOLLOWING
        return follow.status

    def generate_follower_user_ids(self, followed_user_id):
        "Return a generator that produces user ids of users that follow the given user"
        gen = self.dynamo.generate_follower_items(followed_user_id)
        gen = map(lambda item: item['followerUserId'], gen)
        return gen

    def generate_followed_user_ids(self, follower_user_id):
        "Return a generator that produces user ids of users given user follows"
        gen = self.dynamo.generate_followed_items(follower_user_id)
        gen = map(lambda item: item['followedUserId'], gen)
        return gen

    def request_to_follow(self, follower_user, followed_user):
        "Returns the status of the follow request"
        if self.get_follow(follower_user.id, followed_user.id):
            raise exceptions.AlreadyFollowing(follower_user.id, followed_user.id)

        # can't follow a user that has blocked us
        if self.block_manager.is_blocked(followed_user.id, follower_user.id):
            raise exceptions.FollowException(f'User has been blocked by user `{followed_user.id}`')

        # can't follow a user we have blocked
        if self.block_manager.is_blocked(follower_user.id, followed_user.id):
            raise exceptions.FollowException(f'User has blocked user `{followed_user.id}`')

        follow_status = (
            enums.FollowStatus.REQUESTED
            if followed_user.item['privacyStatus'] == UserPrivacyStatus.PRIVATE
            else enums.FollowStatus.FOLLOWING
        )
        follow_item = self.dynamo.add_following(follower_user.id, followed_user.id, follow_status)

        if follow_status == enums.FollowStatus.FOLLOWING:
            # async with dynamo stream handler?
            self.feed_manager.add_users_posts_to_feed(follower_user.id, followed_user.id)
            post = self.post_manager.dynamo.get_next_completed_post_to_expire(followed_user.id)
            if post:
                self.ffs_manager.dynamo.set_all([follower_user.id], post)

        return self.init_follow(follow_item)

    def accept_all_requested_follow_requests(self, followed_user_id):
        for item in self.dynamo.generate_follower_items(followed_user_id, enums.FollowStatus.REQUESTED):
            # can't batch this: dynamo doesn't support batch updates
            self.init_follow(item).accept()

    def delete_all_denied_follow_requests(self, followed_user_id):
        for item in self.dynamo.generate_follower_items(followed_user_id, enums.FollowStatus.DENIED):
            # TODO: do as batch write
            self.dynamo.delete_following(item)

    def reset_follower_items(self, followed_user_id):
        for item in self.dynamo.generate_follower_items(followed_user_id):
            # they were following us, then do an unfollow() to keep their counts correct
            if item['followStatus'] == enums.FollowStatus.FOLLOWING:
                self.init_follow(item).unfollow()
            else:
                # TODO: do as batch write
                self.dynamo.delete_following(item)

    def reset_followed_items(self, follower_user_id):
        for item in self.dynamo.generate_followed_items(follower_user_id):
            # if we were following them, then do an unfollow() to keep their counts correct
            if item['followStatus'] == enums.FollowStatus.FOLLOWING:
                self.init_follow(item).unfollow()
            else:
                # TODO: do as batch write
                self.dynamo.delete_following(item)
