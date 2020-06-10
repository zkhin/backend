import decimal
import logging
import os

import boto3
import pendulum

logger = logging.getLogger()

DYNAMO_TABLE = os.environ.get('DYNAMO_TABLE')


class Migration:
    "Copy trending items to the new trending sub-items"

    pk_prefix = 'trending/'
    from_version = 0
    to_version = 1

    def __init__(self, dynamo_client, dynamo_table):
        self.dynamo_client = dynamo_client
        self.dynamo_table = dynamo_table

    def run(self):
        for item in self.generate_all_items_to_migrate():
            logger.warning(f'Item `{item["partitionKey"]}`: migrating')
            item_id = item['partitionKey'].split('/')[1]
            item_type = item['gsiA1PartitionKey'].split('/')[1]
            score = item['gsiK3SortKey']
            self.add_new_trending(item_type, item_id, score)
            self.update_schema_version(item_id)

    def generate_all_items_to_migrate(self):
        scan_kwargs = {
            'FilterExpression': 'begins_with(partitionKey, :pk_prefix) AND schemaVersion = :sv',
            'ExpressionAttributeValues': {':pk_prefix': self.pk_prefix, ':sv': self.from_version},
        }
        while True:
            paginated = self.dynamo_table.scan(**scan_kwargs)
            for item in paginated['Items']:
                yield item
            if 'LastEvaluatedKey' not in paginated:
                break
            scan_kwargs['ExclusiveStartKey'] = paginated['LastEvaluatedKey']

    def add_new_trending(self, item_type, item_id, score):
        assert item_type in ('post', 'user'), f'Unrecognized item type `{item_type}`'
        assert isinstance(score, decimal.Decimal), 'Boto uses decimals for numbers'
        assert score > 0, 'Score must be greater than 0'

        now_str = pendulum.now('utc').to_iso8601_string()
        query_kwargs = {
            'Item': {
                'partitionKey': f'{item_type}/{item_id}',
                'sortKey': 'trending',
                'schemaVersion': 0,
                'gsiK3PartitionKey': f'{item_type}/trending',
                'gsiK3SortKey': score,
                'lastDeflatedAt': now_str,
                'createdAt': now_str,
            },
            'ConditionExpression': 'attribute_not_exists(partitionKey)',
        }
        try:
            logger.warning(f'Item `trending/{item_id}`: adding new trending for `{item_type}/{item_id}`')
            return self.dynamo_table.put_item(**query_kwargs)
        except self.dynamo_client.exceptions.ConditionalCheckFailedException:
            logger.warning(f'Item `trending/{item_id}`: adding new trending for `{item_type}/{item_id}` - FAILED')
            self.update_existing_trending(item_type, item_id, score)

    def update_existing_trending(self, item_type, item_id, score):
        query_kwargs = {
            'Key': {'partitionKey': f'{item_type}/{item_id}', 'sortKey': 'trending'},
            'UpdateExpression': 'ADD gsiK3SortKey :sta',
            'ExpressionAttributeValues': {':sta': score},
        }
        logger.warning(f'Item `trending/{item_id}`: updating new trending for `{item_type}/{item_id}`')
        return self.dynamo_table.update_item(**query_kwargs)

    def update_schema_version(self, item_id):
        query_kwargs = {
            'Key': {'partitionKey': f'trending/{item_id}', 'sortKey': '-'},
            'UpdateExpression': 'SET schemaVersion = :tsv',
            'ConditionExpression': 'schemaVersion = :fsv',
            'ExpressionAttributeValues': {':tsv': self.to_version, ':fsv': self.from_version},
        }
        logger.warning(f'Item `trending/{item_id}`: updating schema version for `trending/{item_id}`')
        return self.dynamo_table.update_item(**query_kwargs)


if __name__ == '__main__':
    assert DYNAMO_TABLE, 'Must set env variable DYNAMO_TABLE to dynamo table name'

    dynamo_client = boto3.client('dynamodb')
    dynamo_table = boto3.resource('dynamodb').Table(DYNAMO_TABLE)

    migration = Migration(dynamo_client, dynamo_table)
    migration.run()
