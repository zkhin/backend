import logging

import boto3.dynamodb.conditions as conditions
import pendulum

logger = logging.getLogger()


class FlagDynamo:
    def __init__(self, item_type, dynamo_client):
        self.item_type = item_type
        self.client = dynamo_client

    def get(self, item_id, user_id):
        return self.client.get_item({'partitionKey': f'{self.item_type}/{item_id}', 'sortKey': f'flag/{user_id}'})

    def transact_add(self, item_id, user_id, now=None):
        now = now or pendulum.now('utc')
        return {
            'Put': {
                'Item': {
                    'schemaVersion': {'N': '0'},
                    'partitionKey': {'S': f'{self.item_type}/{item_id}'},
                    'sortKey': {'S': f'flag/{user_id}'},
                    'gsiK1PartitionKey': {'S': f'flag/{user_id}'},
                    'gsiK1SortKey': {'S': self.item_type},
                    'createdAt': {'S': now.to_iso8601_string()},
                },
                'ConditionExpression': 'attribute_not_exists(partitionKey)',
            }
        }

    def transact_delete(self, item_id, user_id):
        return {
            'Delete': {
                'Key': {'partitionKey': {'S': f'{self.item_type}/{item_id}'}, 'sortKey': {'S': f'flag/{user_id}'}},
                'ConditionExpression': 'attribute_exists(partitionKey)',
            }
        }

    def delete_all_for_item(self, item_id):
        with self.client.table.batch_writer() as batch:
            for pk in self.generate_by_item(item_id, pks_only=True):
                batch.delete_item(Key=pk)

    def generate_by_item(self, item_id, pks_only=False):
        query_kwargs = {
            'KeyConditionExpression': (
                conditions.Key('partitionKey').eq(f'{self.item_type}/{item_id}')
                & conditions.Key('sortKey').begins_with('flag/')
            ),
        }
        if pks_only:
            query_kwargs['ProjectionExpression'] = 'partitionKey, sortKey'
        return self.client.generate_all_query(query_kwargs)

    def generate_item_ids_by_user(self, user_id):
        query_kwargs = {
            'ProjectionExpression': 'partitionKey',
            'KeyConditionExpression': (
                conditions.Key('gsiK1PartitionKey').eq(f'flag/{user_id}')
                & conditions.Key('gsiK1SortKey').eq(self.item_type)
            ),
            'IndexName': 'GSI-K1',
        }
        prefix_len = len(self.item_type) + 1
        return (i['partitionKey'][prefix_len:] for i in self.client.generate_all_query(query_kwargs))
