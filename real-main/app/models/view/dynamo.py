import logging

import boto3.dynamodb.conditions as conditions

from . import exceptions

logger = logging.getLogger()


class ViewDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def get_view(self, partition_key, user_id, strongly_consistent=False):
        return self.client.get_item({
            'partitionKey': partition_key,
            'sortKey': f'view/{user_id}',
        }, ConsistentRead=strongly_consistent)

    def generate_views(self, partition_key, pks_only=False):
        # no ordering guarantees
        query_kwargs = {
            'KeyConditionExpression': (
                conditions.Key('partitionKey').eq(partition_key)
                & conditions.Key('sortKey').begins_with('view/')
            )
        }
        gen = self.client.generate_all_query(query_kwargs)
        if pks_only:
            gen = ({'partitionKey': item['partitionKey'], 'sortKey': item['sortKey']} for item in gen)
        return gen

    def delete_views(self, view_item_generator):
        with self.client.table.batch_writer() as batch:
            for item in view_item_generator:
                pk = {
                    'partitionKey': item['partitionKey'],
                    'sortKey': item['sortKey'],
                }
                batch.delete_item(Key=pk)

    def add_view(self, partition_key, user_id, view_count, viewed_at):
        viewed_at_str = viewed_at.to_iso8601_string()
        query_kwargs = {
            'Item': {
                'partitionKey': partition_key,
                'sortKey': f'view/{user_id}',
                'gsiK1PartitionKey': partition_key,
                'gsiK1SortKey': f'view/{viewed_at_str}',
                'schemaVersion': 0,
                'viewCount': view_count,
                'firstViewedAt': viewed_at_str,
                'lastViewedAt': viewed_at_str,
            },
        }
        try:
            return self.client.add_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException:
            raise exceptions.ViewAlreadyExists(partition_key, user_id)

    def increment_view(self, partition_key, user_id, view_count, viewed_at):
        query_kwargs = {
            'Key': {
                'partitionKey': partition_key,
                'sortKey': f'view/{user_id}',
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
            raise exceptions.ViewDoesNotExist(partition_key, user_id)
