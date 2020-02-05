import logging

from boto3.dynamodb.conditions import Key

from app.models.post_view import exceptions

logger = logging.getLogger()


class PostViewDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def get_post_view(self, post_id, viewed_by_user_id, strongly_consistent=False):
        return self.client.get_item({
            'partitionKey': f'postView/{post_id}/{viewed_by_user_id}',
            'sortKey': '-',
        }, strongly_consistent=strongly_consistent)

    def generate_post_views(self, post_id):
        query_kwargs = {
            'KeyConditionExpression': Key('gsiA1PartitionKey').eq(f'postView/{post_id}'),
            'IndexName': 'GSI-A1',
        }
        return self.client.generate_all_query(query_kwargs)

    def delete_post_views(self, post_view_item_generator):
        with self.client.table.batch_writer() as batch:
            for item in post_view_item_generator:
                pk = {
                    'partitionKey': item['partitionKey'],
                    'sortKey': item['sortKey'],
                }
                batch.delete_item(Key=pk)

    def add_post_view(self, post_item, viewed_by_user_id, view_count, viewed_at):
        post_id = post_item['postId']
        posted_by_user_id = post_item['postedByUserId']
        viewed_at_str = viewed_at.to_iso8601_string()
        query_kwargs = {
            'Item': {
                'partitionKey': f'postView/{post_id}/{viewed_by_user_id}',
                'sortKey': '-',
                'schemaVersion': 0,
                'gsiA1PartitionKey': f'postView/{post_id}',
                'gsiA1SortKey': viewed_at_str,
                'postId': post_id,
                'postedByUserId': posted_by_user_id,
                'viewedByUserId': viewed_by_user_id,
                'viewCount': view_count,
                'firstViewedAt': viewed_at_str,
                'lastViewedAt': viewed_at_str,
            },
        }
        try:
            return self.client.add_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException:
            raise exceptions.PostViewAlreadyExists(post_id, viewed_by_user_id)

    def add_views_to_post_view(self, post_id, viewed_by_user_id, view_count, viewed_at):
        query_kwargs = {
            'Key': {
                'partitionKey': f'postView/{post_id}/{viewed_by_user_id}',
                'sortKey': '-',
            },
            'UpdateExpression': 'ADD viewCount :vc SET lastViewedAt = :lva',
            'ExpressionAttributeValues': {
                ':vc': view_count,
                ':lva': viewed_at.to_iso8601_string(),
            },
        }
        try:
            return self.client.update_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException:
            raise exceptions.PostViewDoesNotExist(post_id, viewed_by_user_id)
