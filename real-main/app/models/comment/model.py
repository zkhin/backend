import logging

from app.mixins.flag.model import FlagModelMixin
from app.mixins.view.model import ViewModelMixin

from . import exceptions

logger = logging.getLogger()


class Comment(FlagModelMixin, ViewModelMixin):

    exceptions = exceptions
    item_type = 'comment'

    def __init__(
        self,
        comment_item,
        dynamo=None,
        block_manager=None,
        follow_manager=None,
        post_manager=None,
        user_manager=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        if dynamo:
            self.dynamo = dynamo
        if block_manager:
            self.block_manager = block_manager
        if follow_manager:
            self.follow_manager = follow_manager
        if post_manager:
            self.post_manager = post_manager
        if user_manager:
            self.user_manager = user_manager

        self.item = comment_item
        self.id = comment_item['commentId']
        self.user_id = comment_item['userId']
        self.post_id = comment_item['postId']

    @property
    def post(self):
        if not hasattr(self, '_post'):
            self._post = self.post_manager.get_post(self.post_id)
        return self._post

    @property
    def user(self):
        if not hasattr(self, '_user'):
            self._user = self.user_manager.get_user(self.user_id)
        return self._user

    def refresh_item(self, strongly_consistent=False):
        self.item = self.dynamo.get_comment(self.id, strongly_consistent=strongly_consistent)
        return self

    def serialize(self, caller_user_id):
        resp = self.item.copy()
        resp['commentedBy'] = self.user_manager.get_user(self.user_id).serialize(caller_user_id)
        return resp

    def delete(self, deleter_user_id=None, forced=False):
        # users may only delete their own comments or comments on their posts
        if deleter_user_id and deleter_user_id not in (self.post.user_id, self.user_id):
            raise exceptions.CommentException(f'User is not authorized to delete comment `{self.id}`')

        # delete any flags of the comment
        self.flag_dynamo.delete_all_for_item(self.id)

        # order matters to moto (in test suite), but not on dynamo
        transacts = [
            self.user_manager.dynamo.transact_comment_deleted(self.user_id, forced=forced),
            self.post_manager.dynamo.transact_decrement_comment_count(self.post_id),
            self.dynamo.transact_delete_comment(self.id),
        ]
        self.dynamo.client.transact_write_items(transacts)

        # if this comment is being deleted by anyone other than post owner, count it as new comment activity
        if deleter_user_id and deleter_user_id != self.post.user_id:
            self.post.register_new_comment_activity()
        # delete view records on the comment
        self.delete_views()
        return self

    def flag(self, user):
        # if comment is on a post is from a private user then we must be a follower of the post owner
        posted_by_user = self.user_manager.get_user(self.post.user_id)
        if posted_by_user.item['privacyStatus'] != self.user_manager.enums.UserPrivacyStatus.PUBLIC:
            follow = self.follow_manager.get_follow(user.id, self.user_id)
            if not follow or follow.status != self.follow_manager.enums.FollowStatus.FOLLOWING:
                raise exceptions.CommentException(f'User does not have access to comment `{self.id}`')

        super().flag(user)

    def remove_from_flagging(self):
        self.delete(forced=True)

    def is_user_forced_disabling_criteria_met(self):
        return self.user.is_forced_disabling_criteria_met_by_comments()

    def record_view_count(self, user_id, view_count, viewed_at=None):
        # don't count views of user's own comments
        if self.user_id == user_id:
            return False

        is_new_view = super().record_view_count(user_id, view_count, viewed_at=viewed_at)

        if is_new_view:
            self.dynamo.increment_viewed_by_count(self.id)

        return True
