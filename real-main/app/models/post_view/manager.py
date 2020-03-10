from collections import Counter
import logging

import pendulum

from app.models import post, trending, user
from app.models.trending.enums import TrendingItemType

from . import exceptions
from .dynamo import PostViewDynamo

logger = logging.getLogger()


class PostViewManager:

    exceptions = exceptions

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['post_view'] = self
        self.post_manager = managers.get('post') or post.PostManager(clients, managers=managers)
        self.trending_manager = managers.get('trending') or trending.TrendingManager(clients, managers=managers)
        self.user_manager = managers.get('user') or user.UserManager(clients, managers=managers)

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = PostViewDynamo(clients['dynamo'])

    def delete_all_for_post(self, post_id):
        post_view_item_generator = self.dynamo.generate_post_views(post_id)
        self.dynamo.delete_post_views(post_view_item_generator)

    def record_views(self, viewed_by_user_id, post_ids, viewed_at=None):
        viewed_at = viewed_at or pendulum.now('utc')
        grouped_post_ids = dict(Counter(post_ids))
        for post_id, view_count in grouped_post_ids.items():
            self.record_view(viewed_by_user_id, post_id, view_count, viewed_at)

    def record_view(self, viewed_by_user_id, post_id, view_count, viewed_at):
        post = self.post_manager.get_post(post_id)

        if not post:
            logger.warning(f'User `{viewed_by_user_id}` tried to record view(s) on non-existent post `{post_id}`')
            return

        if post.status != post.enums.PostStatus.COMPLETED:
            logger.warning(f'User `{viewed_by_user_id}` tried to record view(s) on non-COMPLETED post `{post_id}`')
            return

        original_post_id = post.item.get('originalPostId', post.id)

        # don't count user's views of their own posts
        if post.user_id == viewed_by_user_id:
            return

        # common case first: try to update an existing post_view_item
        try:
            self.dynamo.add_views_to_post_view(post.id, viewed_by_user_id, view_count, viewed_at)
            return
        except exceptions.PostViewDoesNotExist:
            pass

        # try to add this as a new post view
        try:
            self.dynamo.add_post_view(post.item, viewed_by_user_id, view_count, viewed_at)
        except exceptions.PostViewAlreadyExists:
            # we lost race condition: someone else added post view after our update attempt, so try again to update
            try:
                self.dynamo.add_views_to_post_view(post.id, viewed_by_user_id, view_count, viewed_at)
            except exceptions.PostViewDoesNotExist:
                logger.error(f'Post view for post `{post.id}` and user `{viewed_by_user_id}` does not exist')
            return

        # record the viewedBy on the post and user
        self.post_manager.dynamo.increment_viewed_by_count(post.id)
        self.user_manager.dynamo.increment_post_viewed_by_count(post.user_id)

        # if this is an original post, the trending indexes. If not, then record a view on the original
        if original_post_id == post.id:
            self.trending_manager.record_view_count(TrendingItemType.POST, post.id, 1, now=viewed_at)
            self.trending_manager.record_view_count(TrendingItemType.USER, post.user_id, 1, now=viewed_at)
        else:
            self.record_view(viewed_by_user_id, original_post_id, view_count, viewed_at)
