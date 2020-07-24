import logging

from boto3.dynamodb.conditions import Key

logger = logging.getLogger()


class FeedDynamo:
    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def build_pk(self, feed_user_id, post_id):
        return {'partitionKey': f'user/{feed_user_id}', 'sortKey': f'feed/{post_id}'}

    def parse_pk(self, pk):
        pk_parts = pk['partitionKey'].split('/')
        feed_user_id = pk_parts[1]
        post_id = pk_parts[2] if len(pk_parts) > 2 else pk['sortKey'].split('/')[1]
        return feed_user_id, post_id

    def build_item(self, feed_user_id, post_item):
        "Build a feed item for given user's feed"
        posted_by_user_id = post_item['postedByUserId']
        post_id = post_item['postId']
        item = {
            **self.build_pk(feed_user_id, post_id),
            'schemaVersion': 2,
            'gsiA1PartitionKey': f'feed/{feed_user_id}',
            'gsiA1SortKey': post_item['postedAt'],
            'userId': feed_user_id,
            'postId': post_item['postId'],
            'postedAt': post_item['postedAt'],
            'postedByUserId': posted_by_user_id,
            'gsiK2PartitionKey': f'feed/{feed_user_id}/{posted_by_user_id}',
            'gsiK2SortKey': post_item['postedAt'],
        }
        return item

    def add_posts_to_feed(self, feed_user_id, post_item_generator):
        item_generator = (self.build_item(feed_user_id, post_item) for post_item in post_item_generator)
        self.client.batch_put_items(item_generator)

    def delete_posts_from_feed(self, feed_user_id, post_id_generator):
        key_generator = (self.build_pk(feed_user_id, post_id) for post_id in post_id_generator)
        self.client.batch_delete_items(key_generator)

    def add_post_to_feeds(self, feed_user_id_generator, post_item):
        item_generator = (self.build_item(feed_user_id, post_item) for feed_user_id in feed_user_id_generator)
        self.client.batch_put_items(item_generator)

    def delete_post_from_feeds(self, feed_user_id_generator, post_id):
        key_generator = (self.build_pk(feed_user_id, post_id) for feed_user_id in feed_user_id_generator)
        self.client.batch_delete_items(key_generator)

    def generate_feed(self, feed_user_id):
        query_kwargs = {
            'KeyConditionExpression': Key('gsiA1PartitionKey').eq(f'feed/{feed_user_id}'),
            'IndexName': 'GSI-A1',
        }
        return self.client.generate_all_query(query_kwargs)

    def generate_feed_pks_by_posted_by_user(self, feed_user_id, posted_by_user_id):
        query_kwargs = {
            'KeyConditionExpression': (Key('gsiK2PartitionKey').eq(f'feed/{feed_user_id}/{posted_by_user_id}')),
            'IndexName': 'GSI-K2',
            'ProjectionExpression': 'partitionKey, sortKey',
        }
        return self.client.generate_all_query(query_kwargs)
