import logging

from app.mixins.flag.model import FlagModelMixin

from . import exceptions

logger = logging.getLogger()


class Comment(FlagModelMixin):

    exceptions = exceptions
    item_type = 'comment'

    def __init__(self, comment_item, dynamo=None, block_manager=None, follow_manager=None, post_manager=None,
                 user_manager=None, view_manager=None, **kwargs):
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
        if view_manager:
            self.view_manager = view_manager

        self.item = comment_item
        self.id = comment_item['commentId']
        self.user_id = comment_item['userId']
        self.post_id = comment_item['postId']

    def refresh_item(self, strongly_consistent=False):
        self.item = self.dynamo.get_comment(self.id, strongly_consistent=strongly_consistent)
        return self

    def serialize(self, caller_user_id):
        resp = self.item.copy()
        resp['commentedBy'] = self.user_manager.get_user(self.user_id).serialize(caller_user_id)
        resp['viewedStatus'] = self.view_manager.get_viewed_status(self, caller_user_id)
        return resp

    def delete(self, deleter_user_id):
        "Delete the comment. Set `deleter_user_id` to `None` to override permission checks."
        post = self.post_manager.get_post(self.post_id)

        # users may only delete their own comments or comments on their posts
        if deleter_user_id and deleter_user_id not in (post.user_id, self.user_id):
            raise exceptions.CommentException(f'User is not authorized to delete comment `{self.id}`')

        # delete any flags of the comment
        self.flag_dynamo.delete_all_for_item(self.id)

        # order matters to moto (in test suite), but not on dynamo
        transacts = [
            self.user_manager.dynamo.transact_comment_deleted(self.user_id),
            self.post_manager.dynamo.transact_decrement_comment_count(self.post_id),
            self.dynamo.transact_delete_comment(self.id),
        ]
        self.dynamo.client.transact_write_items(transacts)

        # if this comment is being deleted by anyone other than post owner, count it as new comment activity
        if deleter_user_id and deleter_user_id != post.user_id:
            post.set_new_comment_activity(True)
        # delete view records on the comment
        self.view_manager.delete_views(self.item['partitionKey'])
        return self

    def flag(self, user):
        # if comment is on a post is from a private user then we must be a follower of the post owner
        post = self.post_manager.get_post(self.post_id)
        posted_by_user = self.user_manager.get_user(post.user_id)
        if posted_by_user.item['privacyStatus'] != self.user_manager.enums.UserPrivacyStatus.PUBLIC:
            follow = self.follow_manager.get_follow(user.id, self.user_id)
            if not follow or follow.status != self.follow_manager.enums.FollowStatus.FOLLOWING:
                raise exceptions.CommentException(f'User does not have access to comment `{self.id}`')

        super().flag(user)
