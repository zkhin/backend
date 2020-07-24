import logging

from boto3.dynamodb.conditions import Key

logger = logging.getLogger()


class FeedDynamo:
    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def build_pk(self, feed_user_id, post_id, old_pk=False):
        return (
            {'partitionKey': f'feed/{feed_user_id}/{post_id}', 'sortKey': '-'}
            if old_pk
            else {'partitionKey': f'user/{feed_user_id}', 'sortKey': f'feed/{post_id}'}
        )

    def parse_pk(self, pk):
        pk_parts = pk['partitionKey'].split('/')
        feed_user_id = pk_parts[1]
        post_id = pk_parts[2] if len(pk_parts) > 2 else pk['sortKey'].split('/')[1]
        return feed_user_id, post_id

    def build_item(self, feed_user_id, post_item, old_pk=False):
        "Build a feed item for given user's feed"
        posted_by_user_id = post_item['postedByUserId']
        post_id = post_item['postId']
        item = {
            **self.build_pk(feed_user_id, post_id, old_pk=old_pk),
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

    def add_posts_to_feed(self, feed_user_id, post_item_generator, old_pk=False):
        with self.client.table.batch_writer() as batch:
            for post_item in post_item_generator:
                feed_item = self.build_item(feed_user_id, post_item, old_pk=old_pk)
                batch.put_item(feed_item)

    def delete_posts_from_feed(self, feed_user_id, post_id_generator):
        with self.client.table.batch_writer() as batch:
            for post_id in post_id_generator:
                pk = self.build_pk(feed_user_id, post_id)
                batch.delete_item(Key=pk)
                old_pk = self.build_pk(feed_user_id, post_id, old_pk=True)
                batch.delete_item(Key=old_pk)

    def add_post_to_feeds(self, feed_user_id_generator, post_item, old_pk=False):
        with self.client.table.batch_writer() as batch:
            for feed_user_id in feed_user_id_generator:
                item = self.build_item(feed_user_id, post_item, old_pk=old_pk)
                batch.put_item(item)

    def delete_post_from_feeds(self, feed_user_id_generator, post_id):
        with self.client.table.batch_writer() as batch:
            for feed_user_id in feed_user_id_generator:
                pk = self.build_pk(feed_user_id, post_id)
                batch.delete_item(Key=pk)
                old_pk = self.build_pk(feed_user_id, post_id, old_pk=True)
                batch.delete_item(Key=old_pk)

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
