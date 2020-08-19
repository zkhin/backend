import logging

logger = logging.getLogger()


class FeedDynamo:
    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def build_pk(self, feed_user_id, post_id):
        return {'partitionKey': f'post/{post_id}', 'sortKey': f'feed/{feed_user_id}'}

    def parse_pk(self, pk):
        post_id = pk['partitionKey'].split('/')[1]
        feed_user_id = pk['sortKey'].split('/')[1]
        return post_id, feed_user_id

    def build_item(self, feed_user_id, post_item):
        "Build a feed item for given user's feed"
        posted_by_user_id = post_item['postedByUserId']
        post_id = post_item['postId']
        item = {
            **self.build_pk(feed_user_id, post_id),
            'schemaVersion': 3,
            'gsiA1PartitionKey': f'feed/{feed_user_id}',
            'gsiA1SortKey': post_item['postedAt'],
            'gsiA2PartitionKey': f'feed/{feed_user_id}',
            'gsiA2SortKey': posted_by_user_id,
        }
        return item

    def add_posts_to_feed(self, feed_user_id, post_item_generator):
        item_generator = (self.build_item(feed_user_id, post_item) for post_item in post_item_generator)
        self.client.batch_put_items(item_generator)

    def add_post_to_feeds(self, feed_user_id_generator, post_item):
        "Add the post to all the feeds of the generated user_ids, return a list of those user_ids"
        feed_user_ids = list(feed_user_id_generator)
        item_generator = (self.build_item(feed_user_id, post_item) for feed_user_id in feed_user_ids)
        self.client.batch_put_items(item_generator)
        return feed_user_ids

    def delete_by_post_owner(self, feed_user_id, post_user_id):
        "Delete all feed items by `posted_by_user_id` from the feed of `feed_user_id`"
        pk_generator = self.generate_feed_pks_by_posted_by_user(feed_user_id, post_user_id)
        self.client.batch_delete_items(pk_generator)

    def delete_by_post(self, post_id):
        "Delete all feed items of `post_id`, return a list of affected user_ids"
        pks = list(self.generate_feed_pks_by_post(post_id))
        self.client.batch_delete_items(pk for pk in pks)
        feed_user_ids = [self.parse_pk(pk)[1] for pk in pks]
        return feed_user_ids

    def generate_feed(self, feed_user_id):
        query_kwargs = {
            'KeyConditionExpression': 'gsiA1PartitionKey = :pk',
            'ExpressionAttributeValues': {':pk': f'feed/{feed_user_id}'},
            'IndexName': 'GSI-A1',
        }
        return self.client.generate_all_query(query_kwargs)

    def generate_feed_pks_by_post(self, post_id):
        query_kwargs = {
            'KeyConditionExpression': 'partitionKey = :pk AND begins_with(sortKey, :sk_prefix)',
            'ExpressionAttributeValues': {':pk': f'post/{post_id}', ':sk_prefix': 'feed/'},
            'ProjectionExpression': 'partitionKey, sortKey',
        }
        return self.client.generate_all_query(query_kwargs)

    def generate_feed_pks_by_posted_by_user(self, feed_user_id, posted_by_user_id):
        query_kwargs = {
            'KeyConditionExpression': 'gsiA2PartitionKey = :pk AND gsiA2SortKey = :sk',
            'ExpressionAttributeValues': {':pk': f'feed/{feed_user_id}', ':sk': posted_by_user_id},
            'IndexName': 'GSI-A2',
            'ProjectionExpression': 'partitionKey, sortKey',
        }
        return self.client.generate_all_query(query_kwargs)
