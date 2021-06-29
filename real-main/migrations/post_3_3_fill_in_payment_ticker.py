import json
import logging
import os

import boto3

DYNAMO_TABLE = os.environ.get('DYNAMO_TABLE')

logger = logging.getLogger()


class Migration:
    "For all posts, fill the paymentTicker, paymentTickerRequiredToView and the GSI-A5 index"

    def __init__(self, dynamo_client, dynamo_table):
        self.dynamo_client = dynamo_client
        self.dynamo_table = dynamo_table

    def run(self):
        for post in self.generate_posts_without_post_ticker():
            ad_status = post.get('adStatus', 'NOT_AD')
            if ad_status != 'NOT_AD':
                continue
            self.update_post(post['postId'], post['postedAt'])

    def generate_posts_without_post_ticker(self):
        "Return a generator of all posts that need to be migrated"
        scan_kwargs = {
            'FilterExpression': ' AND '.join(
                [
                    'begins_with(partitionKey, :pk_prefix)',
                    'sortKey = :sk',
                    'attribute_not_exists(paymentTicker)',
                ]
            ),
            'ExpressionAttributeValues': {':pk_prefix': 'post/', ':sk': '-'},
        }
        while True:
            paginated = self.dynamo_table.scan(**scan_kwargs)
            for item in paginated['Items']:
                yield item
            if 'LastEvaluatedKey' not in paginated:
                break
            scan_kwargs['ExclusiveStartKey'] = paginated['LastEvaluatedKey']

    def update_post(self, post_id, posted_at_str):
        query_kwargs = {
            'Key': {'partitionKey': f'post/{post_id}', 'sortKey': '-'},
            'UpdateExpression': 'SET #pt = :pt, #ptrtv = :ptrtv, #pk = :pk, #sk = :sk',
            'ConditionExpression': 'attribute_exists(partitionKey) AND attribute_not_exists(#pt)',
            'ExpressionAttributeNames': {
                '#pt': 'paymentTicker',
                '#ptrtv': 'paymentTickerRequiredToView',
                '#pk': 'gsiA5PartitionKey',
                '#sk': 'gsiA5SortKey',
            },
            'ExpressionAttributeValues': {
                ':pt': 'REAL',
                ':ptrtv': False,
                ':pk': 'postPaymentTicker/REAL',
                ':sk': posted_at_str,
            },
        }
        logger.warning(f'Migrating post `{post_id}`')
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
