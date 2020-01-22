import itertools
import logging

from app.models import follow
from app.models.post.dynamo import PostDynamo

from .dynamo import FeedDynamo

logger = logging.getLogger()


class FeedManager:

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['feed'] = self
        self.follow_manager = managers.get('follow') or follow.FollowManager(clients, managers=managers)

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = FeedDynamo(clients['dynamo'])
            self.post_dynamo = PostDynamo(clients['dynamo'])

    def add_users_posts_to_feed(self, feed_user_id, posted_by_user_id):
        post_item_generator = self.post_dynamo.generate_posts_by_user(posted_by_user_id, completed=True)
        self.dynamo.add_posts_to_feed(feed_user_id, post_item_generator)

    def delete_users_posts_from_feed(self, feed_user_id, posted_by_user_id):
        generator = self.dynamo.generate_feed_pks_by_posted_by_user(feed_user_id, posted_by_user_id)
        generator = map(lambda pk: self.dynamo.parse_pk(pk)[1], generator)
        self.dynamo.delete_posts_from_feed(feed_user_id, generator)

    def add_post_to_followers_feeds(self, followed_user_id, post_item):
        feed_user_id_generator = itertools.chain(
            [followed_user_id],
            self.follow_manager.generate_follower_user_ids(followed_user_id),
        )
        self.dynamo.add_post_to_feeds(feed_user_id_generator, post_item)

    def delete_post_from_followers_feeds(self, followed_user_id, post_id):
        feed_user_id_generator = itertools.chain(
            [followed_user_id],
            self.follow_manager.generate_follower_user_ids(followed_user_id),
        )
        self.dynamo.delete_post_from_feeds(feed_user_id_generator, post_id)
