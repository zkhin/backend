import logging

import pendulum

from .exceptions import CardAlreadyExists

logger = logging.getLogger()


class CardDynamo:
    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def pk(self, card_id):
        return {
            'partitionKey': f'card/{card_id}',
            'sortKey': '-',
        }

    def typed_pk(self, card_id):
        return {
            'partitionKey': {'S': f'card/{card_id}'},
            'sortKey': {'S': '-'},
        }

    def get_card(self, card_id, strongly_consistent=False):
        return self.client.get_item(self.pk(card_id), ConsistentRead=strongly_consistent)

    def add_card(self, card_id, user_id, title, action, sub_title=None, created_at=None, notify_user_at=None):
        created_at = created_at or pendulum.now('utc')
        query_kwargs = {
            'Item': {
                **self.pk(card_id),
                'schemaVersion': 0,
                'gsiA1PartitionKey': f'user/{user_id}',
                'gsiA1SortKey': f'card/{created_at.to_iso8601_string()}',
                'title': title,
                'action': action,
            },
        }
        if sub_title:
            query_kwargs['Item']['subTitle'] = sub_title
        if notify_user_at:
            query_kwargs['Item']['gsiK1PartitionKey'] = 'card'
            query_kwargs['Item']['gsiK1SortKey'] = notify_user_at.to_iso8601_string()
        try:
            return self.client.add_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException:
            raise CardAlreadyExists(card_id)

    def update_title(self, card_id, title):
        query_kwargs = {
            'Key': self.pk(card_id),
            'UpdateExpression': 'SET title = :title',
            'ExpressionAttributeValues': {':title': title},
        }
        return self.client.update_item(query_kwargs)

    def delete_card(self, card_id):
        return self.client.delete_item(self.pk(card_id))

    def clear_notify_user_at(self, card_id):
        query_kwargs = {
            'Key': self.pk(card_id),
            'UpdateExpression': 'REMOVE gsiK1PartitionKey, gsiK1SortKey',
        }
        return self.client.update_item(query_kwargs)

    def generate_cards_by_user(self, user_id, pks_only=False):
        query_kwargs = {
            'KeyConditionExpression': 'gsiA1PartitionKey = :pk AND begins_with(gsiA1SortKey, :sk_prefix)',
            'ExpressionAttributeValues': {':pk': f'user/{user_id}', ':sk_prefix': 'card/'},
            'IndexName': 'GSI-A1',
        }
        gen = self.client.generate_all_query(query_kwargs)
        if pks_only:
            gen = ({'partitionKey': item['partitionKey'], 'sortKey': item['sortKey']} for item in gen)
        return gen

    def generate_card_ids_by_notify_user_at(self, cutoff_at):
        query_kwargs = {
            'KeyConditionExpression': 'gsiK1PartitionKey = :c AND gsiK1SortKey <= :at',
            'ExpressionAttributeValues': {':c': 'card', ':at': cutoff_at.to_iso8601_string()},
            'IndexName': 'GSI-K1',
        }
        gen = self.client.generate_all_query(query_kwargs)
        gen = (item['partitionKey'].split('/')[1] for item in gen)
        return gen
