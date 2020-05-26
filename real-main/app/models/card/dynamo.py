import logging

import boto3.dynamodb.conditions as conditions
import pendulum

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

    def transact_add_card(self, card_id, user_id, title, action, sub_title=None, now=None):
        created_at = now or pendulum.now('utc')
        query_kwargs = {'Put': {
            'Item': {
                'schemaVersion': {'N': '0'},
                'partitionKey': {'S': f'card/{card_id}'},
                'sortKey': {'S': '-'},
                'gsiA1PartitionKey': {'S': f'user/{user_id}'},
                'gsiA1SortKey': {'S': f'card/{created_at.to_iso8601_string()}'},
                'title': {'S': title},
                'action': {'S': action},
            },
            'ConditionExpression': 'attribute_not_exists(partitionKey)',  # no updates, just adds
        }}
        if sub_title:
            query_kwargs['Put']['Item']['subTitle'] = {'S': sub_title}
        return query_kwargs

    def transact_delete_card(self, card_id):
        return {'Delete': {
            'Key': self.typed_pk(card_id),
            'ConditionExpression': 'attribute_exists(partitionKey)',
        }}

    def generate_cards_by_user(self, user_id, pks_only=False):
        query_kwargs = {
            'KeyConditionExpression': (
                conditions.Key('gsiA1PartitionKey').eq(f'user/{user_id}')
                & conditions.Key('gsiA1SortKey').begins_with('card/')
            ),
            'IndexName': 'GSI-A1',
        }
        gen = self.client.generate_all_query(query_kwargs)
        if pks_only:
            gen = ({'partitionKey': item['partitionKey'], 'sortKey': item['sortKey']} for item in gen)
        return gen
