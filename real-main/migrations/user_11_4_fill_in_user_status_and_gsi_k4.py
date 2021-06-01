import json
import logging
import os

import boto3

DYNAMO_TABLE = os.environ.get('DYNAMO_TABLE')

logger = logging.getLogger()


class Migration:
    "For all user items, fill in the userStatus and the GSI-K4 index"

    def __init__(self, dynamo_client, dynamo_table):
        self.dynamo_client = dynamo_client
        self.dynamo_table = dynamo_table

    def run(self):
        for user in self.generate_users():
            user_id = user['partitionKey'].split('/')[1]
            user_status = user.get('userStatus', 'ACTIVE')
            self.update_user(user_id, user_status)

    def generate_users(self):
        "Return a generator of all users that need to be migrated"
        scan_kwargs = {
            'FilterExpression': ' AND '.join(
                [
                    'begins_with(partitionKey, :pk_prefix)',
                    'sortKey = :sk',
                    'attribute_not_exists(gsiK4PartitionKey)',
                ]
            ),
            'ExpressionAttributeValues': {':pk_prefix': 'user/', ':sk': 'profile'},
        }
        while True:
            paginated = self.dynamo_table.scan(**scan_kwargs)
            for item in paginated['Items']:
                yield item
            if 'LastEvaluatedKey' not in paginated:
                break
            scan_kwargs['ExclusiveStartKey'] = paginated['LastEvaluatedKey']

    def update_user(self, user_id, user_status):
        query_kwargs = {
            'Key': {'partitionKey': f'user/{user_id}', 'sortKey': 'profile'},
            'UpdateExpression': 'SET userStatus = :us, gsiK4PartitionKey = :u, gsiK4SortKey = :us',
            'ConditionExpression': 'attribute_exists(partitionKey) AND attribute_not_exists(gsiK4PartitionKey)',
            'ExpressionAttributeValues': {':u': 'user', ':us': user_status},
        }
        logger.warning(f'Migrating user `{user_id}`')
        self.dynamo_table.update_item(**query_kwargs)


def lambda_handler(event, context):
    assert DYNAMO_TABLE, 'Must set env variable DYNAMO_TABLE to dynamo table name'

    dynamo_table = boto3.resource('dynamodb').Table(DYNAMO_TABLE)
    dynamo_client = boto3.client('dynamodb')

    migration = Migration(dynamo_client, dynamo_table)
    migration.run()

    return {'statusCode': 200, 'body': json.dumps('Migration completed successfully')}


if __name__ == '__main__':
    lambda_handler(None, None)
