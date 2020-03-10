import os
import logging

from app.models import block, follow, post, user
from app.models.follow.enums import FollowStatus
from app.models.post.exceptions import PostException, PostDoesNotExist
from app.models.user.enums import UserPrivacyStatus

from . import enums, exceptions
from .dynamo import FlagDynamo

logger = logging.getLogger()

# number of times a post must get flagged before an alert is fired
FLAGGED_ALERT_THRESHOLD = int(os.environ.get('FLAGGED_ALERT_THRESHOLD', 1))


class FlagManager:

    enums = enums
    exceptions = exceptions

    def __init__(self, clients, managers=None, flagged_alert_threshold=FLAGGED_ALERT_THRESHOLD):
        self.flagged_alert_threshold = flagged_alert_threshold
        managers = managers or {}
        managers['flag'] = self
        self.block_manager = managers.get('block') or block.BlockManager(clients, managers=managers)
        self.follow_manager = managers.get('follow') or follow.FollowManager(clients, managers=managers)
        self.post_manager = managers.get('post') or post.PostManager(clients, managers=managers)
        self.user_manager = managers.get('user') or user.UserManager(clients, managers=managers)

        if 'dynamo' in clients:
            self.dynamo = FlagDynamo(clients['dynamo'])

    def flag_post(self, user_id, post):
        # can't flag a post of a user that has blocked us
        posted_by_user = self.user_manager.get_user(post.user_id)
        if self.block_manager.is_blocked(posted_by_user.id, user_id):
            raise exceptions.FlagException(f'User has been blocked by owner of post `{post.id}`')

        # can't flag a post of a user we have blocked
        if self.block_manager.is_blocked(user_id, posted_by_user.id):
            raise exceptions.FlagException(f'User has blocked owner of post `{post.id}`')

        # if the post is from a private user (other than ourselves) then we must be a follower to like the post
        if user_id != posted_by_user.id:
            if posted_by_user.item['privacyStatus'] != UserPrivacyStatus.PUBLIC:
                follow = self.follow_manager.get_follow(user_id, posted_by_user.id)
                if not follow or follow.status != FollowStatus.FOLLOWING:
                    raise exceptions.FlagException(f'User does not have access to post `{post.id}`')

        flag_count = post.item.get('flagCount', 0)
        transacts = [
            self.dynamo.transact_add_flag(post.id, user_id),
            self.post_manager.dynamo.transact_increment_flag_count(post.id),
        ]
        transact_exceptions = [exceptions.AlreadyFlagged(post.id, user_id), PostDoesNotExist(post.id)]
        self.dynamo.client.transact_write_items(transacts, transact_exceptions)
        post.item['flagCount'] = flag_count + 1

        # raise an alert if needed, piggy backing on error alerting for now
        if post.item['flagCount'] >= self.flagged_alert_threshold:
            logger.warning(f'FLAGGED: Post `{post.id}` has been flagged `{post.item["flagCount"]}` time(s).')
        return post

    def unflag_post(self, user_id, post_id):
        transacts = [
            self.dynamo.transact_delete_flag(post_id, user_id),
            self.post_manager.dynamo.transact_decrement_flag_count(post_id),
        ]
        transact_exceptions = [
            exceptions.NotFlagged(post_id, user_id),
            PostException(f'Post `{post_id}` does not exist or has no flagCount'),
        ]
        self.dynamo.client.transact_write_items(transacts, transact_exceptions)

    def unflag_all_by_user(self, user_id):
        for flag_item in self.dynamo.generate_flag_items_by_user(user_id):
            self.unflag_post(user_id, flag_item['postId'])

    def unflag_all_on_post(self, post_id):
        for flag_item in self.dynamo.generate_flag_items_by_post(post_id):
            self.unflag_post(flag_item['flaggerUserId'], post_id)
