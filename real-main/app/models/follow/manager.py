import logging

from app.models import feed, like
from app.models.followed_first_story.dynamo import FollowedFirstStoryDynamo
from app.models.post.dynamo import PostDynamo
from app.models.user.dynamo import UserDynamo
from app.models.user.enums import UserPrivacyStatus

from . import enums, exceptions
from .dynamo import FollowDynamo


logger = logging.getLogger()


class FollowManager:

    enums = enums
    exceptions = exceptions

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['follow'] = self
        self.feed_manager = managers.get('feed') or feed.FeedManager(clients, managers=managers)
        self.like_manager = managers.get('like') or like.LikeManager(clients, managers=managers)

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = FollowDynamo(clients['dynamo'])
            self.user_dynamo = UserDynamo(clients['dynamo'])
            self.ffs_dynamo = FollowedFirstStoryDynamo(clients['dynamo'])
            self.post_dynamo = PostDynamo(clients['dynamo'])

    def get_follow_status(self, follower_user_id, followed_user_id):
        if follower_user_id == followed_user_id:
            return enums.FollowStatus.SELF
        follow_item = self.dynamo.get_following(follower_user_id, followed_user_id)
        if not follow_item:
            return enums.FollowStatus.NOT_FOLLOWING
        return follow_item['followStatus']

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
        if self.dynamo.get_following(follower_user.id, followed_user.id):
            raise exceptions.AlreadyFollowing(follower_user.id, followed_user.id)

        follow_status = (
            enums.FollowStatus.REQUESTED if followed_user.item['privacyStatus'] == UserPrivacyStatus.PRIVATE
            else enums.FollowStatus.FOLLOWING
        )

        transacts = [self.dynamo.transact_add_following(follower_user.id, followed_user.id, follow_status)]
        if follow_status == enums.FollowStatus.FOLLOWING:
            transacts.extend([
                self.user_dynamo.transact_increment_followed_count(follower_user.id),
                self.user_dynamo.transact_increment_follower_count(followed_user.id),
            ])
        self.dynamo.client.transact_write_items(transacts)

        if follow_status == enums.FollowStatus.FOLLOWING:
            # async with sns?
            self.feed_manager.add_users_posts_to_feed(follower_user.id, followed_user.id)
            post = self.post_dynamo.get_next_completed_post_to_expire(followed_user.id)
            if post:
                self.ffs_dynamo.set_all([follower_user.id], post)

        return follow_status

    def unfollow(self, follower_user_id, followed_user_id, force=False):
        "Returns the status of the follow request"
        follow_item = self.dynamo.get_following(follower_user_id, followed_user_id)
        if not follow_item:
            raise exceptions.FollowingDoesNotExist(follower_user_id, followed_user_id)

        if not force and follow_item['followStatus'] == enums.FollowStatus.DENIED:
            raise exceptions.AlreadyHasStatus(follower_user_id, followed_user_id, enums.FollowStatus.DENIED)

        transacts = [self.dynamo.transact_delete_following(follow_item)]
        if follow_item['followStatus'] == enums.FollowStatus.FOLLOWING:
            transacts.extend([
                self.user_dynamo.transact_decrement_followed_count(follower_user_id),
                self.user_dynamo.transact_decrement_follower_count(followed_user_id),
            ])
        self.dynamo.client.transact_write_items(transacts)

        if follow_item['followStatus'] == enums.FollowStatus.FOLLOWING:
            # async with sns?
            self.feed_manager.delete_users_posts_from_feed(follower_user_id, followed_user_id)
            self.ffs_dynamo.delete_all([follower_user_id], followed_user_id)

            # if the user is a private user, then we no longer have access to their posts thus we clear our likes
            followed_user_item = self.user_dynamo.get_user(followed_user_id)
            if followed_user_item['privacyStatus'] == UserPrivacyStatus.PRIVATE:
                self.like_manager.dislike_all_by_user_from_user(follower_user_id, followed_user_id)

        return enums.FollowStatus.NOT_FOLLOWING

    def accept_follow_request(self, follower_user_id, followed_user_id, follow_item=None):
        "Returns the status of the follow request"
        follow_item = follow_item or self.dynamo.get_following(follower_user_id, followed_user_id)
        if not follow_item:
            raise exceptions.FollowingDoesNotExist(follower_user_id, followed_user_id)

        if follow_item['followStatus'] == enums.FollowStatus.FOLLOWING:
            raise exceptions.AlreadyHasStatus(follower_user_id, followed_user_id, enums.FollowStatus.FOLLOWING)

        transacts = [
            self.dynamo.transact_update_following_status(follow_item, enums.FollowStatus.FOLLOWING),
            self.user_dynamo.transact_increment_followed_count(follower_user_id),
            self.user_dynamo.transact_increment_follower_count(followed_user_id),
        ]
        self.dynamo.client.transact_write_items(transacts)

        # async with sns?
        self.feed_manager.add_users_posts_to_feed(follower_user_id, followed_user_id)

        post = self.post_dynamo.get_next_completed_post_to_expire(followed_user_id)
        if post:
            self.ffs_dynamo.set_all([follower_user_id], post)

        return enums.FollowStatus.FOLLOWING

    def accept_all_requested_follow_requests(self, followed_user_id):
        for item in self.dynamo.generate_follower_items(followed_user_id, enums.FollowStatus.REQUESTED):
            try:
                self.accept_follow_request(item['followerUserId'], item['followedUserId'], follow_item=item)
            except Exception:
                logging.exception('Error accepting follow request, continuing')

    def deny_follow_request(self, follower_user_id, followed_user_id):
        "Returns the status of the follow request"
        follow_item = self.dynamo.get_following(follower_user_id, followed_user_id)
        if not follow_item:
            raise exceptions.FollowingDoesNotExist(follower_user_id, followed_user_id)

        if follow_item['followStatus'] == enums.FollowStatus.DENIED:
            raise exceptions.AlreadyHasStatus(follower_user_id, followed_user_id, enums.FollowStatus.DENIED)

        transacts = [self.dynamo.transact_update_following_status(follow_item, enums.FollowStatus.DENIED)]
        if follow_item['followStatus'] == enums.FollowStatus.FOLLOWING:
            transacts.extend([
                self.user_dynamo.transact_decrement_followed_count(follower_user_id),
                self.user_dynamo.transact_decrement_follower_count(followed_user_id),
            ])
        self.dynamo.client.transact_write_items(transacts)

        if follow_item['followStatus'] == enums.FollowStatus.FOLLOWING:
            # async with sns?
            self.feed_manager.delete_users_posts_from_feed(follower_user_id, followed_user_id)
            self.ffs_dynamo.delete_all([follower_user_id], followed_user_id)

            # clear any likes that were droped on the followed's posts by the follower
            self.like_manager.dislike_all_by_user_from_user(follower_user_id, followed_user_id)

        return enums.FollowStatus.DENIED

    def delete_all_denied_follow_requests(self, followed_user_id):
        for item in self.dynamo.generate_follower_items(followed_user_id, enums.FollowStatus.DENIED):
            transacts = [self.dynamo.transact_delete_following(item)]
            self.dynamo.client.transact_write_items(transacts)

    def reset_follower_items(self, followed_user_id):
        for item in self.dynamo.generate_follower_items(followed_user_id):
            # they were following us, then do an unfollow() to keep their counts correct
            if item['followStatus'] == enums.FollowStatus.FOLLOWING:
                self.unfollow(item['followerUserId'], followed_user_id)
            else:
                transacts = [self.dynamo.transact_delete_following(item)]
                self.dynamo.client.transact_write_items(transacts)

    def reset_followed_items(self, follower_user_id):
        for item in self.dynamo.generate_followed_items(follower_user_id):
            # if we were following them, then do an unfollow() to keep their counts correct
            if item['followStatus'] == enums.FollowStatus.FOLLOWING:
                self.unfollow(follower_user_id, item['followedUserId'])
            else:
                transacts = [self.dynamo.transact_delete_following(item)]
                self.dynamo.client.transact_write_items(transacts)
