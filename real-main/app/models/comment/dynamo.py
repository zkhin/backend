import logging

from boto3.dynamodb.conditions import Key
import pendulum

from . import exceptions

logger = logging.getLogger()


class CommentDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def get_comment_pk(self, comment_id):
        return {
            'partitionKey': f'comment/{comment_id}',
            'sortKey': '-',
        }

    def get_comment_view_pk(self, comment_id, viewed_by_user_id):
        return {
            'partitionKey': f'commentView/{comment_id}/{viewed_by_user_id}',
            'sortKey': '-',
        }

    def get_comment(self, comment_id, strongly_consistent=False):
        pk = self.get_comment_pk(comment_id)
        return self.client.get_item(pk, strongly_consistent=strongly_consistent)

    def get_comment_view(self, comment_id, viewed_by_user_id, strongly_consistent=False):
        pk = self.get_comment_view_pk(comment_id, viewed_by_user_id)
        return self.client.get_item(pk, strongly_consistent=strongly_consistent)

    def transact_add_comment(self, comment_id, post_id, user_id, text, text_tags, commented_at=None):
        commented_at = commented_at or pendulum.now('utc')
        commented_at_str = commented_at.to_iso8601_string()
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

    def add_comment_view(self, comment_id, viewed_by_user_id, viewed_at):
        viewed_at_str = viewed_at.to_iso8601_string()
        transacts = [{
            'Put': {
                'Item': {
                    'schemaVersion': {'N': '0'},
                    'partitionKey': {'S': f'commentView/{comment_id}/{viewed_by_user_id}'},
                    'sortKey': {'S': '-'},
                    'gsiK1PartitionKey': {'S': f'commentView/{comment_id}'},
                    'gsiK1SortKey': {'S': viewed_at_str},
                    'commentId': {'S': comment_id},
                    'userId': {'S': viewed_by_user_id},
                    'viewedAt': {'S': viewed_at_str},
                },
                'ConditionExpression': 'attribute_not_exists(partitionKey)',  # no updates, just adds
            },
        }, {
            'ConditionCheck': {
                'Key': {
                    'partitionKey': {'S': f'comment/{comment_id}'},
                    'sortKey': {'S': '-'},
                },
                'ExpressionAttributeValues': {
                    ':uid': {'S': viewed_by_user_id},
                },
                # check comment exists, and that the viewer is not the comment author
                'ConditionExpression': 'attribute_exists(partitionKey) and userId <> :uid',
            },
        }]
        transact_exceptions = [
            exceptions.CommentException('Comment view already exists'),
            exceptions.CommentException('Comment does not exist or exists but viewer is author'),
        ]
        self.client.transact_write_items(transacts, transact_exceptions)

    def generate_comment_view_keys_by_comment(self, comment_id):
        query_kwargs = {
            'KeyConditionExpression': Key('gsiK1PartitionKey').eq(f'commentView/{comment_id}'),
            'IndexName': 'GSI-K1',
        }
        return map(
            lambda item: {'partitionKey': item['partitionKey'], 'sortKey': item['sortKey']},
            self.client.generate_all_query(query_kwargs),
        )

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
