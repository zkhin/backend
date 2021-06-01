import logging
from decimal import Decimal

import pendulum

from . import exceptions
from .enums import ViewType

logger = logging.getLogger()


class ViewDynamo:
    def __init__(self, item_type, dynamo_client):
        self.item_type = item_type
        self.client = dynamo_client

    def key(self, item_id, user_id):
        return {
            'partitionKey': f'{self.item_type}/{item_id}',
            'sortKey': f'view/{user_id}',
        }

    def get_view(self, item_id, user_id, strongly_consistent=False):
        return self.client.get_item(self.key(item_id, user_id), ConsistentRead=strongly_consistent)

    def generate_keys_by_item(self, item_id):
        query_kwargs = {
            'KeyConditionExpression': 'partitionKey = :pk AND begins_with(sortKey, :sk_prefix)',
            'ExpressionAttributeValues': {':pk': f'{self.item_type}/{item_id}', ':sk_prefix': 'view/'},
            'ProjectionExpression': 'partitionKey, sortKey',
        }
        return self.client.generate_all_query(query_kwargs)

    def generate_keys_by_user(self, user_id):
        query_kwargs = {
            'KeyConditionExpression': 'gsiA2PartitionKey = :pk',
            'ExpressionAttributeValues': {':pk': f'{self.item_type}View/{user_id}'},
            'ProjectionExpression': 'partitionKey, sortKey',
            'IndexName': 'GSI-A2',
        }
        return self.client.generate_all_query(query_kwargs)

    def generate_keys_by_user_past_30_days(self, user_id, now=None):
        now = now or pendulum.now('utc')
        past_30_days = now - pendulum.duration(days=30)

        query_kwargs = {
            'KeyConditionExpression': 'gsiA2PartitionKey = :pk AND gsiA2SortKey >= :sk',
            'ExpressionAttributeValues': {
                ':pk': f'{self.item_type}View/{user_id}',
                ':sk': past_30_days.to_iso8601_string(),
            },
            'ProjectionExpression': 'partitionKey, sortKey',
            'IndexName': 'GSI-A2',
        }
        return self.client.generate_all_query(query_kwargs)

    def delete_view(self, item_id, user_id):
        return self.client.delete_item(self.key(item_id, user_id))

    def add_view(self, item_id, user_id, view_count, viewed_at, view_type=None):
        key = self.key(item_id, user_id)
        viewed_at_str = viewed_at.to_iso8601_string()
        query_kwargs = {
            'Item': {
                **key,
                'gsiA1PartitionKey': f'{self.item_type}View/{item_id}',
                'gsiA1SortKey': viewed_at_str,
                'gsiA2PartitionKey': f'{self.item_type}View/{user_id}',
                'gsiA2SortKey': viewed_at_str,
                'schemaVersion': 0,
                'viewCount': view_count,
                'firstViewedAt': viewed_at_str,
                'lastViewedAt': viewed_at_str,
            },
        }

        if view_type == ViewType.THUMBNAIL:
            query_kwargs['Item']['thumbnailViewCount'] = view_count
            query_kwargs['Item']['thumbnailLastViewedAt'] = viewed_at_str
        if view_type == ViewType.FOCUS:
            query_kwargs['Item']['focusViewCount'] = view_count
            query_kwargs['Item']['focusLastViewedAt'] = viewed_at_str

        try:
            return self.client.add_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException as err:
            raise exceptions.ViewAlreadyExists(self.item_type, item_id, user_id) from err

    def increment_view_count(self, item_id, user_id, view_count, viewed_at, view_type=None):
        add_exps = ['viewCount :vc']
        set_exps = ['lastViewedAt = :lva']
        if view_type == ViewType.THUMBNAIL:
            add_exps.append('thumbnailViewCount :vc')
            set_exps.append('thumbnailLastViewedAt = :lva')
        if view_type == ViewType.FOCUS:
            add_exps.append('focusViewCount :vc')
            set_exps.append('focusLastViewedAt = :lva')

        query_kwargs = {
            'Key': self.key(item_id, user_id),
            'UpdateExpression': 'ADD ' + ', '.join(add_exps) + ' SET ' + ', '.join(set_exps),
            'ExpressionAttributeValues': {':vc': view_count, ':lva': viewed_at.to_iso8601_string()},
        }
        try:
            return self.client.update_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException as err:
            raise exceptions.ViewDoesNotExist(self.item_type, item_id, user_id) from err

    def set_royalty_fee(self, item_id, user_id, royalty_fee):
        assert isinstance(royalty_fee, Decimal), 'royalty_fee should be Decimal type'
        query_kwargs = {
            'Key': self.key(item_id, user_id),
            'UpdateExpression': 'SET royaltyFee = :fee',
            'ExpressionAttributeValues': {':fee': royalty_fee},
        }

        try:
            return self.client.update_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException as err:
            raise exceptions.ViewDoesNotExist(self.item_type, item_id, user_id) from err
