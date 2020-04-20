from collections import Counter
import logging

import pendulum

from app.models import comment, chat_message, post, trending, user
from app.models.trending.enums import TrendingItemType

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
            managers.get('chat_message') or chat_message.ChatMessageManager(clients, managers=managers)
        )
        self.comment_manager = managers.get('comment') or comment.CommentManager(clients, managers=managers)
        self.post_manager = managers.get('post') or post.PostManager(clients, managers=managers)
        self.user_manager = managers.get('user') or user.UserManager(clients, managers=managers)
        self.trending_manager = managers.get('trending') or trending.TrendingManager(clients, managers=managers)

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = ViewDynamo(clients['dynamo'])

        self.inst_getters = {
            'chat_message': self.chat_message_manager.get_chat_message,
            'comment': self.comment_manager.get_comment,
            'post': self.post_manager.get_post,
        }

    @property
    def real_user_id(self):
        "The userId of the 'real' user, if they exist"
        if not hasattr(self, '_real_user_id'):
            real_user = self.user_manager.get_user_by_username('real')
            self._real_user_id = real_user.id if real_user else None
        return self._real_user_id

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
        viewed_at = viewed_at or pendulum.now('utc')
        grouped_item_ids = dict(Counter(item_ids))
        for item_id, view_count in grouped_item_ids.items():
            self.record_view(item_type, item_id, user_id, view_count, viewed_at)

    def record_view(self, item_type, item_id, user_id, view_count, viewed_at):
        # verify we can record views on this item
        inst_getter = self.inst_getters.get(item_type)
        if not inst_getter:
            raise Exception(f'Unrecognized item type `{item_type}`')

        inst = inst_getter(item_id)
        if not inst:
            logger.warning(f'Cannot record views by user `{user_id}` on DNE {item_type} `{item_id}`')
            return

        if item_type == 'post':
            if inst.status != inst.enums.PostStatus.COMPLETED:
                logger.warning(f'Cannot record views by user `{user_id}` on non-COMPLETED post `{item_id}`')
                return

        # don't count views on things user owns
        if inst.user_id == user_id:
            return

        is_new_view = False
        partition_key = inst.item['partitionKey']
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

        # special-case stuff for comments
        if item_type == 'comment':
            post = self.post_manager.get_post(inst.post_id)
            if user_id == post.user_id:
                post.set_new_comment_activity(False)

        # special-case stuff for posts
        if item_type == 'post':
            post = inst

            # record the viewedBy on the post and user
            if is_new_view:
                self.post_manager.dynamo.increment_viewed_by_count(post.id)
                self.user_manager.dynamo.increment_post_viewed_by_count(post.user_id)

            # Points towards trending indexes are attributed to the original post
            original_post_id = post.item.get('originalPostId', post.id)
            if original_post_id != post.id:
                return self.record_view('post', original_post_id, user_id, view_count, viewed_at)

            # don't add the trending indexes if the post is more than a 24 hrs old
            if (viewed_at - post.posted_at > pendulum.duration(hours=24)):
                return

            # don't add posts that failed verification
            if post.item.get('isVerified') is False:
                return

            # don't add real user or their posts to trending indexes
            if post.user_id == self.real_user_id:
                return

            self.trending_manager.record_view_count(TrendingItemType.POST, post.id, now=viewed_at)
            self.trending_manager.record_view_count(TrendingItemType.USER, post.user_id, now=viewed_at)
