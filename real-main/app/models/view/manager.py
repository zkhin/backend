from collections import Counter
import logging

import pendulum

from app import models

from . import enums, exceptions
from .dynamo import ViewDynamo

logger = logging.getLogger()


class ViewManager:

    enums = enums
    exceptions = exceptions

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['view'] = self
        self.chat_message_manager = (
            managers.get('chat_message') or models.ChatMessageManager(clients, managers=managers)
        )
        self.comment_manager = managers.get('comment') or models.CommentManager(clients, managers=managers)
        self.post_manager = managers.get('post') or models.PostManager(clients, managers=managers)
        self.user_manager = managers.get('user') or models.UserManager(clients, managers=managers)
        self.trending_manager = managers.get('trending') or models.TrendingManager(clients, managers=managers)

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = ViewDynamo(clients['dynamo'])

    def get_viewed_status(self, inst, user_id):
        if inst.user_id == user_id:  # author of the message
            return enums.ViewedStatus.VIEWED
        elif self.dynamo.get_view(inst.item['partitionKey'], user_id):
            return enums.ViewedStatus.VIEWED
        else:
            return enums.ViewedStatus.NOT_VIEWED

    def delete_views(self, partition_key):
        view_item_generator = self.dynamo.generate_views(partition_key)
        self.dynamo.delete_views(view_item_generator)

    def record_views(self, item_type, item_ids, user_id, viewed_at=None):
        if item_type == 'chat_message':
            recorder = self.record_view_for_chat_message
        elif item_type == 'comment':
            recorder = self.record_view_for_comment
        elif item_type == 'post':
            recorder = self.record_view_for_post
        else:
            raise AssertionError(f'Unknown item type `{item_type}`')

        viewed_at = viewed_at or pendulum.now('utc')
        grouped_item_ids = dict(Counter(item_ids))
        for item_id, view_count in grouped_item_ids.items():
            recorder(item_id, user_id, view_count, viewed_at)

    def record_view_for_comment(self, comment_id, user_id, view_count, viewed_at):
        comment = self.comment_manager.get_comment(comment_id)
        if not comment:
            logger.warning(f'Cannot record view(s) by user `{user_id}` on DNE comment `{comment_id}`')
            return

        # don't count views of user's own comments
        if comment.user_id == user_id:
            return

        self.write_view_to_dynamo(comment.item['partitionKey'], user_id, view_count, viewed_at)

        post = self.post_manager.get_post(comment.post_id)
        if user_id == post.user_id:
            post.set_new_comment_activity(False)

    def record_view_for_chat_message(self, message_id, user_id, view_count, viewed_at):
        message = self.chat_message_manager.get_chat_message(message_id)
        if not message:
            logger.warning(f'Cannot record view(s) by user `{user_id}` on DNE message `{message_id}`')
            return

        # don't count views of user's own chat messages
        if message.user_id == user_id:
            return

        self.write_view_to_dynamo(message.item['partitionKey'], user_id, view_count, viewed_at)

    def record_view_for_post(self, post_id, user_id, view_count, viewed_at):
        post = self.post_manager.get_post(post_id)
        if not post:
            logger.warning(f'Cannot record view(s) by user `{user_id}` on DNE post `{post_id}`')
            return

        if post.status != post.enums.PostStatus.COMPLETED:
            logger.warning(f'Cannot record views by user `{user_id}` on non-COMPLETED post `{post_id}`')
            return

        # only count views of other user's posts
        if post.user_id != user_id:
            is_new_view = self.write_view_to_dynamo(post.item['partitionKey'], user_id, view_count, viewed_at)

            # record the viewedBy on the post and user
            if is_new_view:
                self.post_manager.dynamo.increment_viewed_by_count(post.id)
                self.user_manager.dynamo.increment_post_viewed_by_count(post.user_id)

            # If this is a non-original post, count this like a view of the original post as well
            original_post_id = post.item.get('originalPostId', post.id)
            if original_post_id != post.id:
                self.record_view_for_post(original_post_id, user_id, view_count, viewed_at)

        # let the treinding indexes know about this view
        self.trending_manager.increment_scores_for_post(post, now=viewed_at)

    def write_view_to_dynamo(self, partition_key, user_id, view_count, viewed_at):
        is_new_view = False
        view_item = self.dynamo.get_view(partition_key, user_id)
        if view_item:
            self.dynamo.increment_view(partition_key, user_id, view_count, viewed_at)
        else:
            try:
                self.dynamo.add_view(partition_key, user_id, view_count, viewed_at)
            except exceptions.ViewAlreadyExists:
                # we lost a race condition to add the view, so still need to record our data
                self.dynamo.increment_view(partition_key, user_id, view_count, viewed_at)
            else:
                is_new_view = True
        return is_new_view
