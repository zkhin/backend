import logging

import pendulum

from app import models
from app.mixins.base import ManagerBase
from app.mixins.flag.manager import FlagManagerMixin
from app.models.follower.enums import FollowStatus
from app.models.user.enums import UserPrivacyStatus

from .dynamo import CommentDynamo
from .exceptions import CommentException
from .model import Comment

logger = logging.getLogger()


class CommentManager(FlagManagerMixin, ManagerBase):

    item_type = 'comment'

    def __init__(self, clients, managers=None):
        super().__init__(clients, managers=managers)
        managers = managers or {}
        managers['comment'] = self
        self.block_manager = managers.get('block') or models.BlockManager(clients, managers=managers)
        self.follower_manager = managers.get('follower') or models.FollowerManager(clients, managers=managers)
        self.post_manager = managers.get('post') or models.PostManager(clients, managers=managers)
        self.user_manager = managers.get('user') or models.UserManager(clients, managers=managers)

        if 'dynamo' in clients:
            self.dynamo = CommentDynamo(clients['dynamo'])

    def get_model(self, item_id):
        return self.get_comment(item_id)

    def get_comment(self, comment_id):
        comment_item = self.dynamo.get_comment(comment_id)
        return self.init_comment(comment_item) if comment_item else None

    def init_comment(self, comment_item):
        kwargs = {
            'dynamo': getattr(self, 'dynamo', None),
            'flag_dynamo': getattr(self, 'flag_dynamo', None),
            'block_manager': self.block_manager,
            'follower_manager': self.follower_manager,
            'post_manager': self.post_manager,
            'user_manager': self.user_manager,
        }
        return Comment(comment_item, **kwargs)

    def add_comment(self, comment_id, post_id, user_id, text, now=None):
        now = now or pendulum.now('utc')

        post = self.post_manager.get_post(post_id)
        if not post:
            raise CommentException(f'Post `{post_id}` does not exist')

        if post.item.get('commentsDisabled', False):
            raise CommentException(f'Comments are disabled on post `{post_id}`')

        if user_id != post.user_id:

            # can't comment if there's a blocking relationship, either direction
            if self.block_manager.is_blocked(post.user_id, user_id):
                raise CommentException(f'Post owner `{post.user_id}` has blocked user `{user_id}`')
            if self.block_manager.is_blocked(user_id, post.user_id):
                raise CommentException(f'User `{user_id}` has blocked post owner `{post.user_id}`')

            # if post owner is private, must be a follower to comment
            poster = self.user_manager.get_user(post.user_id)
            if poster.item['privacyStatus'] == UserPrivacyStatus.PRIVATE:
                follow = self.follower_manager.get_follow(user_id, post.user_id)
                if not follow or follow.status != FollowStatus.FOLLOWING:
                    msg = f'Post owner `{post.user_id}` is private and user `{user_id}` is not a follower'
                    raise CommentException(msg)

        text_tags = self.user_manager.get_text_tags(text)
        comment_item = self.dynamo.add_comment(comment_id, post_id, user_id, text, text_tags, commented_at=now)
        return self.init_comment(comment_item)

    def on_user_delete_delete_all_by_user(self, user_id, old_item):
        for comment_item in self.dynamo.generate_by_user(user_id):
            self.init_comment(comment_item).delete()

    def delete_all_on_post(self, post_id):
        for comment_item in self.dynamo.generate_by_post(post_id):
            self.init_comment(comment_item).delete()

    def on_flag_add(self, comment_id, new_item):
        comment_item = self.dynamo.increment_flag_count(comment_id)
        comment = self.init_comment(comment_item)

        user_id = new_item['sortKey'].split('/')[1]
        flagger = self.user_manager.get_user(user_id)

        # force delete the comment?
        if (
            flagger.id == comment.post.user_id
            or flagger.username in self.flag_admin_usernames
            or comment.is_crowdsourced_forced_removal_criteria_met()
        ):
            logger.warning(f'Force deleting comment `{comment_id}` from flagging')
            comment.delete(forced=True)
