from datetime import datetime
import logging

from boto3.dynamodb.conditions import Key

from app.lib import datetime as real_datetime

from . import exceptions

logger = logging.getLogger()


class BlockDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def get_block(self, blocker_user_id, blocked_user_id):
        return self.client.get_item({
            'partitionKey': f'block/{blocker_user_id}/{blocked_user_id}',
            'sortKey': '-',
        })

    def add_block(self, blocker_user_id, blocked_user_id, now=None):
        now = now or datetime.utcnow()
        blocked_at_str = real_datetime.serialize(now)
        query_kwargs = {
            'Item': {
                'schemaVersion': 0,
                'partitionKey': f'block/{blocker_user_id}/{blocked_user_id}',
                'sortKey': '-',
                'gsiA1PartitionKey': f'block/{blocker_user_id}',
                'gsiA1SortKey': blocked_at_str,
                'gsiA2PartitionKey': f'block/{blocked_user_id}',
                'gsiA2SortKey': blocked_at_str,
                'blockerUserId': blocker_user_id,
                'blockedUserId': blocked_user_id,
                'blockedAt': blocked_at_str,
            },
        }
        try:
            return self.client.add_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException:
            raise exceptions.AlreadyBlocked(blocker_user_id, blocked_user_id)

    def delete_block(self, blocker_user_id, blocked_user_id):
        query_kwargs = {
            'Key': {
                'partitionKey': f'block/{blocker_user_id}/{blocked_user_id}',
                'sortKey': '-',
            },
            'ConditionExpression': 'attribute_exists(partitionKey)',  # fail if doesnt exist
        }
        try:
            return self.client.delete_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException:
            raise exceptions.NotBlocked(blocker_user_id, blocked_user_id)

    def generate_blocks_by_blocker(self, blocker_user_id):
        query_kwargs = {
            'KeyConditionExpression': Key('gsiA1PartitionKey').eq(f'block/{blocker_user_id}'),
            'IndexName': 'GSI-A1',
        }
        return self.client.generate_all_query(query_kwargs)

    def generate_blocks_by_blocked(self, blocked_user_id):
        query_kwargs = {
            'KeyConditionExpression': Key('gsiA2PartitionKey').eq(f'block/{blocked_user_id}'),
            'IndexName': 'GSI-A2',
        }
        return self.client.generate_all_query(query_kwargs)
