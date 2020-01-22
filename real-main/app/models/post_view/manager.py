from collections import Counter
from datetime import datetime
import logging

from app.models import trending
from app.models.post.dynamo import PostDynamo
from app.models.trending.enums import TrendingItemType
from app.models.user.dynamo import UserDynamo

from . import exceptions
from .dynamo import PostViewDynamo

logger = logging.getLogger()


class PostViewManager:

    exceptions = exceptions

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['post_view'] = self
        self.trending_manager = managers.get('trending') or trending.TrendingManager(clients, managers=managers)

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = PostViewDynamo(clients['dynamo'])
            self.post_dynamo = PostDynamo(clients['dynamo'])
            self.user_dynamo = UserDynamo(clients['dynamo'])

    def delete_all_for_post(self, post_id):
        post_view_item_generator = self.dynamo.generate_post_views(post_id)
        self.dynamo.delete_post_views(post_view_item_generator)

    def record_views(self, viewed_by_user_id, post_ids, viewed_at=None):
        viewed_at = viewed_at or datetime.utcnow()
        grouped_post_ids = dict(Counter(post_ids))
        for post_id, view_count in grouped_post_ids.items():
            self.record_view(viewed_by_user_id, post_id, view_count, viewed_at)

    def record_view(self, viewed_by_user_id, post_id, view_count, viewed_at):
        post_view_item = self.dynamo.get_post_view(post_id, viewed_by_user_id)

        # is this the first time this user has viewed this post?
        if not post_view_item:
            post_item = self.post_dynamo.get_post(post_id)

            if not post_item:
                logger.warning(f'User `{viewed_by_user_id}` tried to record view(s) on non-existent post `{post_id}`')
                return
            posted_by_user_id = post_item['postedByUserId']

            # create the new post view item
            try:
                self.dynamo.add_post_view(post_item, viewed_by_user_id, view_count, viewed_at)
            except exceptions.PostViewAlreadyExists:
                # another thread added the post view in between our last read and this write
                post_view_item = self.dynamo.get_post_view(post_id, viewed_by_user_id, strongly_consistent=True)
                if not post_view_item:
                    msg = f'Post view for post `{post_id}` and user `{viewed_by_user_id}` should exist but does not?'
                    logger.warning(msg)
            else:
                # record the viewedBy on the post and user
                self.post_dynamo.increment_viewed_by_count(post_id)
                self.user_dynamo.increment_post_viewed_by_count(posted_by_user_id)

                # update the trending indexes
                self.trending_manager.record_view_count(TrendingItemType.POST, post_id, 1)
                self.trending_manager.record_view_count(TrendingItemType.USER, posted_by_user_id, 1)

        # is this _not_ the first this user has viewed this post?
        if post_view_item:
            self.dynamo.add_views_to_post_view(post_id, viewed_by_user_id, view_count, viewed_at)
