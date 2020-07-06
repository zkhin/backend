import logging

import pendulum
from boto3.dynamodb.conditions import Key

from .exceptions import AlreadyFlagged, NotFlagged

logger = logging.getLogger()


class FlagDynamo:
    def __init__(self, item_type, dynamo_client):
        self.item_type = item_type
        self.client = dynamo_client

    def get(self, item_id, user_id):
        return self.client.get_item({'partitionKey': f'{self.item_type}/{item_id}', 'sortKey': f'flag/{user_id}'})

    def add(self, item_id, user_id, now=None):
        now = now or pendulum.now('utc')
        query_kwargs = {
            'Item': {
                'schemaVersion': 0,
                'partitionKey': f'{self.item_type}/{item_id}',
                'sortKey': f'flag/{user_id}',
                'gsiK1PartitionKey': f'flag/{user_id}',
                'gsiK1SortKey': self.item_type,
                'createdAt': now.to_iso8601_string(),
            },
        }
        try:
            return self.client.add_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException:
            raise AlreadyFlagged(self.item_type, item_id, user_id)

    def delete(self, item_id, user_id):
        deleted = self.client.delete_item(
            {'partitionKey': f'{self.item_type}/{item_id}', 'sortKey': f'flag/{user_id}'}
        )
        if not deleted:
            raise NotFlagged(self.item_type, item_id, user_id)

    def delete_all_for_item(self, item_id):
        with self.client.table.batch_writer() as batch:
            for pk in self.generate_by_item(item_id, pks_only=True):
                batch.delete_item(Key=pk)

    def generate_by_item(self, item_id, pks_only=False):
        query_kwargs = {
            'KeyConditionExpression': (
                Key('partitionKey').eq(f'{self.item_type}/{item_id}') & Key('sortKey').begins_with('flag/')
            ),
        }
        if pks_only:
            query_kwargs['ProjectionExpression'] = 'partitionKey, sortKey'
        return self.client.generate_all_query(query_kwargs)

    def generate_item_ids_by_user(self, user_id):
        query_kwargs = {
            'ProjectionExpression': 'partitionKey',
            'KeyConditionExpression': (
                Key('gsiK1PartitionKey').eq(f'flag/{user_id}') & Key('gsiK1SortKey').eq(self.item_type)
            ),
            'IndexName': 'GSI-K1',
        }
        prefix_len = len(self.item_type) + 1
        return (i['partitionKey'][prefix_len:] for i in self.client.generate_all_query(query_kwargs))
