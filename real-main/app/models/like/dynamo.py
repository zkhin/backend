import functools
import logging

import boto3.dynamodb.conditions as conditions
import pendulum

logger = logging.getLogger()


class LikeDynamo:
    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def parse_pk(self, pk):
        _, liked_by_user_id, post_id = pk['partitionKey'].split('/')
        return liked_by_user_id, post_id

    def get_like(self, liked_by_user_id, post_id):
        return self.client.get_item({'partitionKey': f'like/{liked_by_user_id}/{post_id}', 'sortKey': '-'})

    def transact_add_like(self, liked_by_user_id, post_item, like_status, now=None):
        now = now or pendulum.now('utc')
        liked_at_str = now.to_iso8601_string()
        post_id = post_item['postId']
        posted_by_user_id = post_item['postedByUserId']

        add_like_item = {
            'Put': {
                'Item': {
                    'schemaVersion': {'N': '1'},
                    'partitionKey': {'S': f'like/{liked_by_user_id}/{post_id}'},
                    'sortKey': {'S': '-'},
                    'gsiA1PartitionKey': {'S': f'like/{liked_by_user_id}'},
                    'gsiA1SortKey': {'S': f'{like_status}/{liked_at_str}'},
                    'gsiA2PartitionKey': {'S': f'like/{post_id}'},
                    'gsiA2SortKey': {'S': f'{like_status}/{liked_at_str}'},
                    'gsiK2PartitionKey': {'S': f'like/{posted_by_user_id}'},
                    'gsiK2SortKey': {'S': liked_by_user_id},
                    'likedByUserId': {'S': liked_by_user_id},
                    'likeStatus': {'S': like_status},
                    'likedAt': {'S': liked_at_str},
                    'postId': {'S': post_id},
                },
                'ConditionExpression': 'attribute_not_exists(partitionKey)',  # only creates
            },
        }
        return add_like_item

    def transact_delete_like(self, liked_by_user_id, post_id, like_status):
        return {
            'Delete': {
                'Key': {'partitionKey': {'S': f'like/{liked_by_user_id}/{post_id}'}, 'sortKey': {'S': '-'}},
                'ConditionExpression': 'likeStatus = :like_status',
                'ExpressionAttributeValues': {':like_status': {'S': like_status}},
            },
        }

    def generate_of_post(self, post_id):
        query_kwargs = {
            'KeyConditionExpression': conditions.Key('gsiA2PartitionKey').eq(f'like/{post_id}'),
            'IndexName': 'GSI-A2',
        }
        return self.client.generate_all_query(query_kwargs)

    def generate_by_liked_by(self, liked_by_user_id):
        query_kwargs = {
            'KeyConditionExpression': conditions.Key('gsiA1PartitionKey').eq(f'like/{liked_by_user_id}'),
            'IndexName': 'GSI-A1',
        }
        return self.client.generate_all_query(query_kwargs)

    def generate_pks_by_liked_by_for_posted_by(self, liked_by_user_id, posted_by_user_id):
        key_conditions = [
            conditions.Key('gsiK2PartitionKey').eq(f'like/{posted_by_user_id}'),
            conditions.Key('gsiK2SortKey').eq(liked_by_user_id),
        ]
        query_kwargs = {
            'KeyConditionExpression': functools.reduce(lambda a, b: a & b, key_conditions),
            'IndexName': 'GSI-K2',
            # Note: moto (mocking framework used in test suite) needs this projection expression,
            #       else it returns the whole item even though the dynamo index is keys-only
            'ProjectionExpression': 'partitionKey, sortKey',
        }
        return self.client.generate_all_query(query_kwargs)
