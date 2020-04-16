from functools import reduce
import logging

from boto3.dynamodb.conditions import Key
import pendulum

from . import exceptions

logger = logging.getLogger()


class TrendingDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def get_trending(self, item_id):
        return self.client.get_item({
            'partitionKey': f'trending/{item_id}',
            'sortKey': '-',
        })

    def delete_trending(self, item_id):
        "Delete a trending, if it exists. If it doesn't, no-op."
        return self.client.delete_item({
            'Key': {
                'partitionKey': f'trending/{item_id}',
                'sortKey': '-',
            },
        })

    def create_trending(self, item_type, item_id, view_count, now=None):
        now = now or pendulum.now('utc')
        query_kwargs = {
            'Item': {
                'partitionKey': f'trending/{item_id}',
                'sortKey': '-',
                'gsiA1PartitionKey': f'trending/{item_type}',
                'gsiA1SortKey': now.to_iso8601_string(),
                'gsiK3PartitionKey': f'trending/{item_type}',
                'gsiK3SortKey': view_count,
                'schemaVersion': 0,
                'pendingViewCount': 0,
            },
        }
        try:
            return self.client.add_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException:
            raise exceptions.TrendingAlreadyExists(item_id)

    def increment_trending_score(self, item_id, view_count, now=None):
        "Add view counts directly to the trending score"
        now = now or pendulum.now('utc')
        query_kwargs = {
            'Key': {
                'partitionKey': f'trending/{item_id}',
                'sortKey': '-',
            },
            'UpdateExpression': 'ADD gsiK3SortKey :cnt',
            'ConditionExpression': 'gsiA1SortKey >= :gsia1sk',
            'ExpressionAttributeValues': {
                ':cnt': view_count,
                ':gsia1sk': now.to_iso8601_string(),
            },
        }
        try:
            return self.client.update_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException:
            msg = 'Trending does not exist or exists with a lastIndexedAt that is not exactly now'
            raise exceptions.TrendingException(msg)

    def increment_trending_pending_view_count(self, item_id, view_count, now=None):
        now = now or pendulum.now('utc')
        query_kwargs = {
            'Key': {
                'partitionKey': f'trending/{item_id}',
                'sortKey': '-',
            },
            'UpdateExpression': 'ADD pendingViewCount :cnt',
            'ConditionExpression': 'gsiA1SortKey < :gsia1sk',
            'ExpressionAttributeValues': {
                ':cnt': view_count,
                ':gsia1sk': now.to_iso8601_string(),
            },
        }
        try:
            return self.client.update_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException:
            msg = 'Trending does not exist or exists with a lastIndexedAt in now or in the future'
            raise exceptions.TrendingException(msg)

    def update_trending_score(self, item_id, score, new_last_indexed_at, old_last_indexed_at, view_count_change_abs):
        query_kwargs = {
            'Key': {
                'partitionKey': f'trending/{item_id}',
                'sortKey': '-',
            },
            'UpdateExpression': (
                'SET gsiA1SortKey = :nslua, gsiK3SortKey = :score ADD pendingViewCount :npvc'
            ),
            'ExpressionAttributeValues': {
                ':nslua': new_last_indexed_at.to_iso8601_string(),
                ':oslua': old_last_indexed_at.to_iso8601_string(),
                ':score': score,
                ':npvc': -view_count_change_abs,
                ':ppvc': view_count_change_abs,
            },
            'ConditionExpression': (
                'gsiA1SortKey = :oslua and pendingViewCount >= :ppvc'
            ),
        }
        return self.client.update_item(query_kwargs)

    def generate_trendings(self, item_type, max_last_indexed_at=None):
        "Generator of trendings. max_last_index_at is exclusive"
        key_conditions = [Key('gsiA1PartitionKey').eq(f'trending/{item_type}')]
        if max_last_indexed_at is not None:
            key_conditions.append(Key('gsiA1SortKey').lt(max_last_indexed_at.to_iso8601_string()))
        query_kwargs = {
            'KeyConditionExpression': reduce(lambda a, b: a & b, key_conditions),
            'IndexName': 'GSI-A1',
        }
        return self.client.generate_all_query(query_kwargs)
