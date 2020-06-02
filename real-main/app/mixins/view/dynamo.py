import logging

import boto3.dynamodb.conditions as conditions

from . import exceptions

logger = logging.getLogger()


class ViewDynamo:
    def __init__(self, item_type, dynamo_client):
        self.item_type = item_type
        self.client = dynamo_client

    def pk(self, item_id, user_id):
        return {
            'partitionKey': f'{self.item_type}/{item_id}',
            'sortKey': f'view/{user_id}',
        }

    def get_view(self, item_id, user_id, strongly_consistent=False):
        return self.client.get_item(self.pk(item_id, user_id), ConsistentRead=strongly_consistent)

    def generate_views(self, item_id, pks_only=False):
        # no ordering guarantees
        pk = self.pk(item_id, None)
        query_kwargs = {
            'KeyConditionExpression': (
                conditions.Key('partitionKey').eq(pk['partitionKey'])
                & conditions.Key('sortKey').begins_with('view/')
            )
        }
        gen = self.client.generate_all_query(query_kwargs)
        if pks_only:
            gen = ({'partitionKey': item['partitionKey'], 'sortKey': item['sortKey']} for item in gen)
        return gen

    def delete_views(self, view_pk_generator):
        with self.client.table.batch_writer() as batch:
            for pk in view_pk_generator:
                batch.delete_item(Key=pk)

    def add_view(self, item_id, user_id, view_count, viewed_at):
        pk = self.pk(item_id, user_id)
        viewed_at_str = viewed_at.to_iso8601_string()
        query_kwargs = {
            'Item': {
                'partitionKey': pk['partitionKey'],
                'sortKey': pk['sortKey'],
                'gsiK1PartitionKey': pk['partitionKey'],
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
            raise exceptions.ViewAlreadyExists(self.item_type, item_id, user_id)

    def increment_view_count(self, item_id, user_id, view_count, viewed_at):
        pk = self.pk(item_id, user_id)
        query_kwargs = {
            'Key': pk,
            'UpdateExpression': 'ADD viewCount :vc SET lastViewedAt = :lva',
            'ExpressionAttributeValues': {':vc': view_count, ':lva': viewed_at.to_iso8601_string(),},
        }
        try:
            return self.client.update_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException:
            raise exceptions.ViewDoesNotExist(self.item_type, item_id, user_id)
