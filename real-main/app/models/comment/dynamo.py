from datetime import datetime
import logging

from boto3.dynamodb.conditions import Key

from app.lib import datetime as real_datetime

logger = logging.getLogger()


class CommentDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def get_comment(self, comment_id, strongly_consistent=False):
        return self.client.get_item({
            'partitionKey': f'comment/{comment_id}',
            'sortKey': '-',
        }, strongly_consistent=strongly_consistent)

    def transact_add_comment(self, comment_id, post_id, user_id, text, text_tags, commented_at=None):
        commented_at = commented_at or datetime.utcnow()
        commented_at_str = real_datetime.serialize(commented_at)
        return {'Put': {
            'Item': {
                'schemaVersion': {'N': '0'},
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
            'Key': {
                'partitionKey': {'S': f'comment/{comment_id}'},
                'sortKey': {'S': '-'},
            },
            'ConditionExpression': 'attribute_exists(partitionKey)',
        }}

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
