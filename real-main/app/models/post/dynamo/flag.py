import logging

from boto3.dynamodb.conditions import Key
import pendulum

logger = logging.getLogger()


class PostFlagDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def get(self, post_id, user_id):
        return self.client.get_item({
            'partitionKey': f'post/{post_id}',
            'sortKey': f'flag/{user_id}',
        })

    def transact_add(self, post_id, user_id, now=None):
        now = now or pendulum.now('utc')
        return {
            'Put': {
                'Item': {
                    'schemaVersion': {'N': '0'},
                    'partitionKey': {'S': f'post/{post_id}'},
                    'sortKey': {'S': f'flag/{user_id}'},
                    'gsiK1PartitionKey': {'S': f'flag/{user_id}'},
                    'gsiK1SortKey': {'S': '-'},
                    'createdAt': {'S': now.to_iso8601_string()},
                },
                'ConditionExpression': 'attribute_not_exists(partitionKey)',
            }
        }

    def transact_delete(self, post_id, user_id):
        return {
            'Delete': {
                'Key': {
                    'partitionKey': {'S': f'post/{post_id}'},
                    'sortKey': {'S': f'flag/{user_id}'},
                },
                'ConditionExpression': 'attribute_exists(partitionKey)',
            }
        }

    def delete_all_for_post(self, post_id):
        with self.client.table.batch_writer() as batch:
            for pk in self.generate_by_post(post_id, pks_only=True):
                batch.delete_item(Key=pk)

    def generate_by_post(self, post_id, pks_only=False):
        query_kwargs = {
            'KeyConditionExpression': (
                Key('partitionKey').eq(f'post/{post_id}')
                & Key('sortKey').begins_with('flag/')
            ),
        }
        if pks_only:
            query_kwargs['ProjectionExpression'] = 'partitionKey, sortKey'
        return self.client.generate_all_query(query_kwargs)

    def generate_post_ids_by_user(self, user_id):
        query_kwargs = {
            'ProjectionExpression': 'partitionKey',
            'KeyConditionExpression': Key('gsiK1PartitionKey').eq(f'flag/{user_id}'),
            'IndexName': 'GSI-K1',
        }
        return (i['partitionKey'][5:] for i in self.client.generate_all_query(query_kwargs))
