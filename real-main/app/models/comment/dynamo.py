import logging

import boto3.dynamodb.conditions as conditions
import pendulum

from . import exceptions

logger = logging.getLogger()


class CommentDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def pk(self, comment_id):
        return {
            'partitionKey': f'comment/{comment_id}',
            'sortKey': '-',
        }

    def typed_pk(self, comment_id):
        return {
            'partitionKey': {'S': f'comment/{comment_id}'},
            'sortKey': {'S': '-'},
        }

    def get_comment(self, comment_id, strongly_consistent=False):
        return self.client.get_item(self.pk(comment_id), ConsistentRead=strongly_consistent)

    def transact_add_comment(self, comment_id, post_id, user_id, text, text_tags, commented_at=None):
        commented_at = commented_at or pendulum.now('utc')
        commented_at_str = commented_at.to_iso8601_string()
        return {'Put': {
            'Item': {
                'schemaVersion': {'N': '1'},
                'partitionKey': {'S': f'comment/{comment_id}'},
                'sortKey': {'S': '-'},
                'gsiA1PartitionKey': {'S': f'comment/{post_id}'},
                'gsiA1SortKey': {'S': commented_at_str},
                'gsiA2PartitionKey': {'S': f'comment/{user_id}'},
                'gsiA2SortKey': {'S': commented_at_str},
                'commentId': {'S': comment_id},
                'postId': {'S': post_id},
                'userId': {'S': user_id},
                'commentedAt': {'S': commented_at_str},
                'text': {'S': text},
                'textTags': {'L': [
                    {'M': {
                        'tag': {'S': text_tag['tag']},
                        'userId': {'S': text_tag['userId']},
                    }}
                    for text_tag in text_tags
                ]},
            },
            'ConditionExpression': 'attribute_not_exists(partitionKey)',  # no updates, just adds
        }}

    def transact_delete_comment(self, comment_id):
        return {'Delete': {
            'Key': self.typed_pk(comment_id),
            'ConditionExpression': 'attribute_exists(partitionKey)',
        }}

    def transact_increment_flag_count(self, comment_id):
        return {
            'Update': {
                'Key': self.typed_pk(comment_id),
                'UpdateExpression': 'ADD flagCount :one',
                'ExpressionAttributeValues': {
                    ':one': {'N': '1'},
                },
                'ConditionExpression': 'attribute_exists(partitionKey)',  # only updates, no creates
            }
        }

    def transact_decrement_flag_count(self, comment_id):
        return {
            'Update': {
                'Key': self.typed_pk(comment_id),
                'UpdateExpression': 'ADD flagCount :neg_one',
                'ExpressionAttributeValues': {
                    ':neg_one': {'N': '-1'},
                    ':zero': {'N': '0'},
                },
                'ConditionExpression': 'attribute_exists(partitionKey) AND flagCount > :zero',
            }
        }

    def increment_viewed_by_count(self, comment_id):
        query_kwargs = {
            'Key': self.pk(comment_id),
            'UpdateExpression': 'ADD viewedByCount :one',
            'ExpressionAttributeValues': {':one': 1},
        }
        try:
            return self.client.update_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException:
            raise exceptions.CommentDoesNotExist(comment_id)

    def generate_by_post(self, post_id):
        query_kwargs = {
            'KeyConditionExpression': conditions.Key('gsiA1PartitionKey').eq(f'comment/{post_id}'),
            'IndexName': 'GSI-A1',
        }
        return self.client.generate_all_query(query_kwargs)

    def generate_by_user(self, user_id):
        query_kwargs = {
            'KeyConditionExpression': conditions.Key('gsiA2PartitionKey').eq(f'comment/{user_id}'),
            'IndexName': 'GSI-A2',
        }
        return self.client.generate_all_query(query_kwargs)
