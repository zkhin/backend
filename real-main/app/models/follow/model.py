import logging

from app.models.user.enums import UserPrivacyStatus

from . import enums, exceptions
from .enums import FollowStatus

logger = logging.getLogger()


class Follow:

    enums = enums
    exceptions = exceptions

    def __init__(self, follow_item, follow_dynamo, feed_manager=None, ffs_manager=None, like_manager=None,
                 post_manager=None, user_manager=None):
        self.dynamo = follow_dynamo
        self.followed_user_id = follow_item['followedUserId']
        self.follower_user_id = follow_item['followerUserId']
        self.item = follow_item
        if feed_manager:
            self.feed_manager = feed_manager
        if ffs_manager:
            self.ffs_manager = ffs_manager
        if like_manager:
            self.like_manager = like_manager
        if post_manager:
            self.post_manager = post_manager
        if user_manager:
            self.user_manager = user_manager

    @property
    def status(self):
        return self.item['followStatus'] if self.item else FollowStatus.NOT_FOLLOWING

    def refresh_item(self):
        self.item = self.dynamo.get_following(self.follower_user_id, self.followed_user_id)
        return self

    def unfollow(self, force=False):
        "Returns the status of the follow request"
        if not force and self.status == FollowStatus.DENIED:
            raise exceptions.AlreadyHasStatus(self.follower_user_id, self.followed_user_id, FollowStatus.DENIED)

        transacts = [self.dynamo.transact_delete_following(self.item)]
        if self.status == FollowStatus.FOLLOWING:
            transacts.extend([
                self.user_manager.dynamo.transact_decrement_followed_count(self.follower_user_id),
                self.user_manager.dynamo.transact_decrement_follower_count(self.followed_user_id),
            ])
        self.dynamo.client.transact_write_items(transacts)

        if self.status == FollowStatus.FOLLOWING:
            # async with sns?
            self.feed_manager.delete_users_posts_from_feed(self.follower_user_id, self.followed_user_id)
            self.ffs_manager.dynamo.delete_all([self.follower_user_id], self.followed_user_id)

            # if the user is a private user, then we no longer have access to their posts thus we clear our likes
            followed_user_item = self.user_manager.dynamo.get_user(self.followed_user_id)
            if followed_user_item['privacyStatus'] == UserPrivacyStatus.PRIVATE:
                self.like_manager.dislike_all_by_user_from_user(self.follower_user_id, self.followed_user_id)

        self.item['followStatus'] = FollowStatus.NOT_FOLLOWING
        return self

    def accept(self):
        "Returns the status of the follow request"
        if self.status == FollowStatus.FOLLOWING:
            raise exceptions.AlreadyHasStatus(self.follower_user_id, self.followed_user_id, FollowStatus.FOLLOWING)

        transacts = [
            self.dynamo.transact_update_following_status(self.item, FollowStatus.FOLLOWING),
            self.user_manager.dynamo.transact_increment_followed_count(self.follower_user_id),
            self.user_manager.dynamo.transact_increment_follower_count(self.followed_user_id),
        ]
        self.dynamo.client.transact_write_items(transacts)

        # async with sns?
        self.feed_manager.add_users_posts_to_feed(self.follower_user_id, self.followed_user_id)

        post = self.post_manager.dynamo.get_next_completed_post_to_expire(self.followed_user_id)
        if post:
            self.ffs_manager.dynamo.set_all([self.follower_user_id], post)

        self.item['followStatus'] = FollowStatus.FOLLOWING
        return self

    def deny(self):
        "Returns the status of the follow request"
        if self.status == FollowStatus.DENIED:
            raise exceptions.AlreadyHasStatus(self.follower_user_id, self.followed_user_id, FollowStatus.DENIED)

        transacts = [self.dynamo.transact_update_following_status(self.item, FollowStatus.DENIED)]
        if self.status == FollowStatus.FOLLOWING:
            transacts.extend([
                self.user_manager.dynamo.transact_decrement_followed_count(self.follower_user_id),
                self.user_manager.dynamo.transact_decrement_follower_count(self.followed_user_id),
            ])
        self.dynamo.client.transact_write_items(transacts)

        if self.status == FollowStatus.FOLLOWING:
            # async with sns?
            self.feed_manager.delete_users_posts_from_feed(self.follower_user_id, self.followed_user_id)
            self.ffs_manager.dynamo.delete_all([self.follower_user_id], self.followed_user_id)

            # clear any likes that were droped on the followed's posts by the follower
            self.like_manager.dislike_all_by_user_from_user(self.follower_user_id, self.followed_user_id)

        self.item['followStatus'] = FollowStatus.DENIED
        return self
