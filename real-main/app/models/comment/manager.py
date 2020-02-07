import logging

import pendulum

from app.models import block, follow, post, user

from . import exceptions
from .dynamo import CommentDynamo
from .model import Comment

logger = logging.getLogger()


class CommentManager:

    exceptions = exceptions

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['comment'] = self
        self.block_manager = managers.get('block') or block.BlockManager(clients, managers=managers)
        self.user_manager = managers.get('user') or user.UserManager(clients, managers=managers)

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = CommentDynamo(clients['dynamo'])
            self.follow_dynamo = follow.dynamo.FollowDynamo(clients['dynamo'])
            self.post_dynamo = post.dynamo.PostDynamo(clients['dynamo'])

    def get_comment(self, comment_id):
        comment_item = self.dynamo.get_comment(comment_id)
        return self.init_comment(comment_item) if comment_item else None

    def init_comment(self, comment_item):
        return Comment(comment_item, self.clients, user_manager=self.user_manager)

    def add_comment(self, comment_id, post_id, user_id, text, now=None):
        now = now or pendulum.now('utc')

        post_item = self.post_dynamo.get_post(post_id)
        if not post_item:
            raise exceptions.CommentException(f'Post `{post_id}` does not exist')

        if post_item.get('commentsDisabled', False):
            raise exceptions.CommentException(f'Comments are disabled on post `{post_id}`')

        posted_by_user_id = post_item['postedByUserId']
        if user_id != posted_by_user_id:

            # can't comment if there's a blocking relationship, either direction
            if self.block_manager.is_blocked(posted_by_user_id, user_id):
                raise exceptions.CommentException(f'Post owner `{posted_by_user_id}` has blocked user `{user_id}`')
            if self.block_manager.is_blocked(user_id, posted_by_user_id):
                raise exceptions.CommentException(f'User `{user_id}` has blocked post owner `{posted_by_user_id}`')

            # if post owner is private, must be a follower to comment
            poster = self.user_manager.get_user(posted_by_user_id)
            if poster.item['privacyStatus'] == user.enums.UserPrivacyStatus.PRIVATE:
                follow_item = self.follow_dynamo.get_following(user_id, posted_by_user_id)
                follow_status = follow_item['followStatus'] if follow_item else None
                if follow_status != follow.enums.FollowStatus.FOLLOWING:
                    msg = f'Post owner `{posted_by_user_id}` is private and user `{user_id}` is not a follower'
                    raise exceptions.CommentException(msg)

        text_tags = self.user_manager.get_text_tags(text)
        transacts = [
            self.dynamo.transact_add_comment(comment_id, post_id, user_id, text, text_tags, commented_at=now),
            self.post_dynamo.transact_increment_comment_count(post_id),
        ]
        transact_exceptions = [
            exceptions.CommentException(f'Unable to add comment with id `{comment_id}`... id already used?'),
            exceptions.CommentException('Unable to increment Post.commentCount'),
        ]
        self.dynamo.client.transact_write_items(transacts, transact_exceptions)

        comment_item = self.dynamo.get_comment(comment_id, strongly_consistent=True)
        return self.init_comment(comment_item)

    def delete_comment(self, comment_id, deleter_user_id):
        comment = self.get_comment(comment_id)
        if not comment:
            raise exceptions.CommentException(f'No comment with id `{comment_id}` found')

        # users may only delete their own comments or comments on their posts
        if comment.item['userId'] != deleter_user_id:
            post_item = self.post_dynamo.get_post(comment.item['postId'])
            if post_item['postedByUserId'] != deleter_user_id:
                raise exceptions.CommentException(f'User is not authorized to delete comment `{comment_id}`')

        comment.delete()
        return comment

    def delete_all_by_user(self, user_id):
        for comment_item in self.dynamo.generate_by_user(user_id):
            self.init_comment(comment_item).delete()

    def delete_all_on_post(self, post_id):
        for comment_item in self.dynamo.generate_by_post(post_id):
            self.init_comment(comment_item).delete()
