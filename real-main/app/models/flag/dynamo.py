import logging

from boto3.dynamodb.conditions import Key
import pendulum

logger = logging.getLogger()


class FlagDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def get_flag(self, post_id, user_id):
        return self.client.get_item({
            'partitionKey': f'flag/{user_id}/{post_id}',
            'sortKey': '-',
        })

    def transact_add_flag(self, post_id, user_id, now=None):
        now = now or pendulum.now('utc')
        flagged_at_str = now.to_iso8601_string()
        return {
            'Put': {
                'Item': {
                    'schemaVersion': {'N': '1'},
                    'partitionKey': {'S': f'flag/{user_id}/{post_id}'},
                    'sortKey': {'S': '-'},
                    'gsiA1PartitionKey': {'S': f'flag/{user_id}'},
                    'gsiA1SortKey': {'S': flagged_at_str},
                    'gsiA2PartitionKey': {'S': f'flag/{post_id}'},
                    'gsiA2SortKey': {'S': flagged_at_str},
                    'postId': {'S': post_id},
                    'flaggerUserId': {'S': user_id},
                    'flaggedAt': {'S': flagged_at_str},
                },
                'ConditionExpression': 'attribute_not_exists(partitionKey)',  # only creates
            }
        }

    def transact_delete_flag(self, post_id, user_id):
        return {
            'Delete': {
                'Key': {
                    'partitionKey': {'S': f'flag/{user_id}/{post_id}'},
                    'sortKey': {'S': '-'},
                },
                'ConditionExpression': 'attribute_exists(partitionKey)',
            }
        }

    def generate_flag_items_by_user(self, user_id):
        query_kwargs = {
            'KeyConditionExpression': Key('gsiA1PartitionKey').eq(f'flag/{user_id}'),
            'IndexName': 'GSI-A1',
        }
        return self.client.generate_all_query(query_kwargs)

    def generate_flag_items_by_post(self, post_id):
        query_kwargs = {
            'KeyConditionExpression': Key('gsiA2PartitionKey').eq(f'flag/{post_id}'),
            'IndexName': 'GSI-A2',
        }
        return self.client.generate_all_query(query_kwargs)
