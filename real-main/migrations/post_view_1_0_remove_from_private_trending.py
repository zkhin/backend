import json
import logging
import os

import boto3

logger = logging.getLogger()

DYNAMO_TABLE = os.environ.get('DYNAMO_TABLE')


class Migration:
    "Remove post view records for users who viewed a post from private user"

    def __init__(self, dynamo_client, dynamo_table):
        self.dynamo_client = dynamo_client
        self.dynamo_table = dynamo_table

    def run(self):
        for post_pk in self.generate_trending_post_pks():
            post_id = post_pk.split('/')[1]
            post = self.get_post(post_pk)
            posted_by_user_id = post.get('postedByUserId')
            poster = self.get_user(posted_by_user_id)

            if poster.get('privacyStatus') == 'PRIVATE':
                for view_sk in self.generate_post_view_records_sks(post_id):
                    user_id = view_sk.split('/')[1]
                    following = self.get_following(user_id, posted_by_user_id)
                    if following and following['Item'].get('followStatus') == 'FOLLOWING':
                        continue

                    logger.warning(f'Post `{post_pk}` User `user/{user_id}`: deleting view record')
                    self.delete_post_view_record(post_pk, user_id)

    def generate_trending_post_pks(self):
        query_kwargs = {
            'KeyConditionExpression': 'gsiA4PartitionKey = :gsia4pk',
            'ExpressionAttributeValues': {':gsia4pk': 'post/trending'},
            'IndexName': 'GSI-A4',
        }
        while True:
            paginated = self.dynamo_table.query(**query_kwargs)
            for item in paginated['Items']:
                yield item['partitionKey']
            if 'LastEvaluatedKey' not in paginated:
                break
            query_kwargs['ExclusiveStartKey'] = paginated['LastEvaluatedKey']

    def generate_post_view_records_sks(self, post_id):
        query_kwargs = {
            'KeyConditionExpression': 'gsiA1PartitionKey = :gsia1pk',
            'ExpressionAttributeValues': {':gsia1pk': f'postView/{post_id}'},
            'IndexName': 'GSI-A1',
        }
        while True:
            paginated = self.dynamo_table.query(**query_kwargs)
            for item in paginated['Items']:
                yield item['sortKey']
            if 'LastEvaluatedKey' not in paginated:
                break
            query_kwargs['ExclusiveStartKey'] = paginated['LastEvaluatedKey']

    def get_post(self, post_pk):
        key = {'partitionKey': post_pk, 'sortKey': '-'}
        return self.dynamo_table.get_item(Key=key)['Item']

    def get_user(self, user_id):
        key = {'partitionKey': f'user/{user_id}', 'sortKey': 'profile'}
        return self.dynamo_table.get_item(Key=key)['Item']

    def get_following(self, follower_user_id, followed_user_id):
        key = {'partitionKey': f'user/{followed_user_id}', 'sortKey': f'follower/{follower_user_id}'}
        return self.dynamo_table.get_item(Key=key)

    def delete_post_view_record(self, post_pk, user_id):
        key = {'partitionKey': post_pk, 'sortKey': f'view/{user_id}'}
        self.dynamo_table.delete_item(Key=key)


def lambda_handler(event, context):
    assert DYNAMO_TABLE, 'Must set env variable DYNAMO_TABLE to dynamo table name'

    dynamo_table = boto3.resource('dynamodb').Table(DYNAMO_TABLE)
    dynamo_client = boto3.client('dynamodb')

    migration = Migration(dynamo_client, dynamo_table)
    migration.run()

    return {'statusCode': 200, 'body': json.dumps('Migration completed successfully')}


if __name__ == '__main__':
    lambda_handler(None, None)
