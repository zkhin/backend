import logging

import pendulum
from boto3.dynamodb.conditions import Key

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

    def add_comment(self, comment_id, post_id, user_id, text, text_tags, commented_at=None):
        commented_at = commented_at or pendulum.now('utc')
        commented_at_str = commented_at.to_iso8601_string()
        query_kwargs = {
            'Item': {
                **self.pk(comment_id),
                'schemaVersion': 1,
                'gsiA1PartitionKey': f'comment/{post_id}',
                'gsiA1SortKey': commented_at_str,
                'gsiA2PartitionKey': f'comment/{user_id}',
                'gsiA2SortKey': commented_at_str,
                'commentId': comment_id,
                'postId': post_id,
                'userId': user_id,
                'commentedAt': commented_at_str,
                'text': text,
                'textTags': text_tags,
            },
        }
        try:
            return self.client.add_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException:
            raise exceptions.CommentAlreadyExists(comment_id)

    def delete_comment(self, comment_id):
        return self.client.delete_item(self.pk(comment_id))

    def _increment_count(self, attribute_name, comment_id):
        query_kwargs = {
            'Key': self.pk(comment_id),
            'UpdateExpression': 'ADD #attrName :one',
            'ExpressionAttributeNames': {'#attrName': attribute_name},
            'ExpressionAttributeValues': {':one': 1},
            'ConditionExpression': 'attribute_exists(partitionKey)',
        }
        return self.client.update_item(query_kwargs)

    def _decrement_count(self, attribute_name, comment_id, fail_soft=False):
        query_kwargs = {
            'Key': self.pk(comment_id),
            'UpdateExpression': 'ADD #attrName :neg_one',
            'ExpressionAttributeNames': {'#attrName': attribute_name},
            'ExpressionAttributeValues': {':neg_one': -1, ':zero': 0},
            'ConditionExpression': 'attribute_exists(partitionKey) AND #attrName > :zero',
        }
        try:
            return self.client.update_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException:
            if fail_soft:
                logger.warning(f'Failed to decrement {attribute_name} for comment `{comment_id}`')
                return
            raise

    def increment_flag_count(self, comment_id):
        return self._increment_count('flagCount', comment_id)

    def decrement_flag_count(self, comment_id, fail_soft=False):
        return self._decrement_count('flagCount', comment_id, fail_soft=fail_soft)

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
            'KeyConditionExpression': Key('gsiA1PartitionKey').eq(f'comment/{post_id}'),
            'IndexName': 'GSI-A1',
        }
        return self.client.generate_all_query(query_kwargs)

    def generate_by_user(self, user_id):
        query_kwargs = {
            'KeyConditionExpression': Key('gsiA2PartitionKey').eq(f'comment/{user_id}'),
            'IndexName': 'GSI-A2',
        }
        return self.client.generate_all_query(query_kwargs)
