import functools
import logging

import pendulum
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()


class FollowDynamo:
    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def new_pk(self, follower_user_id, followed_user_id):
        return {
            'partitionKey': f'user/{followed_user_id}',
            'sortKey': f'follower/{follower_user_id}',
        }

    def new_typed_pk(self, follower_user_id, followed_user_id):
        return {
            'partitionKey': {'S': f'user/{followed_user_id}'},
            'sortKey': {'S': f'follower/{follower_user_id}'},
        }

    def old_pk(self, follower_user_id, followed_user_id):
        return {
            'partitionKey': f'following/{follower_user_id}/{followed_user_id}',
            'sortKey': '-',
        }

    def old_typed_pk(self, follower_user_id, followed_user_id):
        return {
            'partitionKey': {'S': f'following/{follower_user_id}/{followed_user_id}'},
            'sortKey': {'S': '-'},
        }

    def get_following(self, follower_user_id, followed_user_id, strongly_consistent=False):
        new_pk = self.new_pk(follower_user_id, followed_user_id)
        old_pk = self.old_pk(follower_user_id, followed_user_id)
        new_item = self.client.get_item(new_pk, ConsistentRead=strongly_consistent)
        return new_item if new_item else self.client.get_item(old_pk, ConsistentRead=strongly_consistent)

    def add_following(self, follower_user_id, followed_user_id, follow_status, use_old_pk=False):
        followed_at_str = pendulum.now('utc').to_iso8601_string()
        pk_getter = self.old_pk if use_old_pk else self.new_pk
        query_kwargs = {
            'Item': {
                **pk_getter(follower_user_id, followed_user_id),
                'schemaVersion': 1,
                'gsiA1PartitionKey': f'follower/{follower_user_id}',
                'gsiA1SortKey': f'{follow_status}/{followed_at_str}',
                'gsiA2PartitionKey': f'followed/{followed_user_id}',
                'gsiA2SortKey': f'{follow_status}/{followed_at_str}',
                'followedAt': followed_at_str,
                'followStatus': follow_status,
                'followerUserId': follower_user_id,
                'followedUserId': followed_user_id,
            },
        }
        return self.client.add_item(query_kwargs)

    def update_following_status(self, follow_item, follow_status):
        key = {k: follow_item[k] for k in ('partitionKey', 'sortKey')}
        query_kwargs = {
            'Key': key,
            'UpdateExpression': 'SET followStatus = :status, gsiA1SortKey = :sk, gsiA2SortKey = :sk',
            'ExpressionAttributeValues': {
                ':status': follow_status,
                ':sk': f'{follow_status}/{follow_item["followedAt"]}',
            },
        }
        return self.client.update_item(query_kwargs)

    def delete_following(self, follow_item):
        key = {k: follow_item[k] for k in ('partitionKey', 'sortKey')}
        return self.client.delete_item(key)

    def generate_followed_items(self, user_id, follow_status=None, limit=None, next_token=None):
        "Generate items that represent a followed of the given user (that the given user is the follower)"
        key_conditions = [Key('gsiA1PartitionKey').eq(f'follower/{user_id}')]
        if follow_status is not None:
            key_conditions.append(Key('gsiA1SortKey').begins_with(follow_status + '/'))
        query_kwargs = {
            'KeyConditionExpression': functools.reduce(lambda a, b: a & b, key_conditions),
            'IndexName': 'GSI-A1',
        }
        return self.client.generate_all_query(query_kwargs)

    def generate_follower_items(self, user_id, follow_status=None, limit=None, next_token=None):
        "Generate items that represent a follower of the given user (that the given user is the followed)"
        key_conditions = [Key('gsiA2PartitionKey').eq(f'followed/{user_id}')]
        if follow_status is not None:
            key_conditions.append(Key('gsiA2SortKey').begins_with(follow_status + '/'))
        query_kwargs = {
            'KeyConditionExpression': functools.reduce(lambda a, b: a & b, key_conditions),
            'IndexName': 'GSI-A2',
        }
        return self.client.generate_all_query(query_kwargs)
