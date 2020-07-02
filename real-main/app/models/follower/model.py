import logging

from app.models.user.enums import UserPrivacyStatus

from .enums import FollowStatus
from .exceptions import FollowerAlreadyHasStatus

logger = logging.getLogger()


class Follower:
    def __init__(
        self,
        follow_item,
        follow_dynamo,
        first_story_dynamo,
        feed_manager=None,
        like_manager=None,
        post_manager=None,
        user_manager=None,
    ):
        self.dynamo = follow_dynamo
        self.first_story_dynamo = first_story_dynamo
        self.followed_user_id = follow_item['followedUserId']
        self.follower_user_id = follow_item['followerUserId']
        self.item = follow_item
        if feed_manager:
            self.feed_manager = feed_manager
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
            raise FollowerAlreadyHasStatus(self.follower_user_id, self.followed_user_id, FollowStatus.DENIED)
        self.dynamo.delete_following(self.item)

        if self.status == FollowStatus.FOLLOWING:
            # async with dynamo stream handler?
            self.feed_manager.delete_users_posts_from_feed(self.follower_user_id, self.followed_user_id)
            self.first_story_dynamo.delete_all([self.follower_user_id], self.followed_user_id)

            # if the user is a private user, then we no longer have access to their posts thus we clear our likes
            followed_user_item = self.user_manager.dynamo.get_user(self.followed_user_id)
            if followed_user_item['privacyStatus'] == UserPrivacyStatus.PRIVATE:
                self.like_manager.dislike_all_by_user_from_user(self.follower_user_id, self.followed_user_id)

        self.item['followStatus'] = FollowStatus.NOT_FOLLOWING
        return self

    def accept(self):
        "Returns the status of the follow request"
        if self.status == FollowStatus.FOLLOWING:
            raise FollowerAlreadyHasStatus(self.follower_user_id, self.followed_user_id, FollowStatus.FOLLOWING)
        self.dynamo.update_following_status(self.item, FollowStatus.FOLLOWING)

        # async with dynamo stream handler?
        self.feed_manager.add_users_posts_to_feed(self.follower_user_id, self.followed_user_id)

        post = self.post_manager.dynamo.get_next_completed_post_to_expire(self.followed_user_id)
        if post:
            self.first_story_dynamo.set_all([self.follower_user_id], post)

        self.item['followStatus'] = FollowStatus.FOLLOWING
        return self

    def deny(self):
        "Returns the status of the follow request"
        if self.status == FollowStatus.DENIED:
            raise FollowerAlreadyHasStatus(self.follower_user_id, self.followed_user_id, FollowStatus.DENIED)
        self.dynamo.update_following_status(self.item, FollowStatus.DENIED)

        if self.status == FollowStatus.FOLLOWING:
            # async with sns?
            self.feed_manager.delete_users_posts_from_feed(self.follower_user_id, self.followed_user_id)
            self.first_story_dynamo.delete_all([self.follower_user_id], self.followed_user_id)

            # clear any likes that were droped on the followed's posts by the follower
            self.like_manager.dislike_all_by_user_from_user(self.follower_user_id, self.followed_user_id)

        self.item['followStatus'] = FollowStatus.DENIED
        return self
