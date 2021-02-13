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
        for pv in self.generate_all_post_views():
            self.migrate_post_view(pv)

    def generate_all_post_views(self):
        "Return a generator of all items in the table that pass the filter"
        scan_kwargs = {
            'FilterExpression': ' AND '.join(
                [
                    'begins_with(partitionKey, :pk_prefix)',
                    'begins_with(sortKey, :sk_prefix)',
                ]
            ),
            'ExpressionAttributeValues': {':pk_prefix': 'post/', ':sk_prefix': 'view/'},
        }
        while True:
            paginated = self.dynamo_table.scan(**scan_kwargs)
            for item in paginated['Items']:
                yield item
            if 'LastEvaluatedKey' not in paginated:
                break
            scan_kwargs['ExclusiveStartKey'] = paginated['LastEvaluatedKey']

    def migrate_post_view(self, pv):
        post_pk = pv['partitionKey']
        user_id = pv['sortKey'].split('/')[1]

        post = self.get_post(post_pk)
        posted_by_user_id = post.get('postedByUserId')
        poster = self.get_user(posted_by_user_id)

        if poster.get('privacyStatus') == 'PRIVATE':
            following = self.get_following(user_id, posted_by_user_id)
            if following and following['Item'].get('followStatus') == 'FOLLOWING':
                return

            logger.warning(f'Post `{post_pk}` User `user/{user_id}`: deleting view record')
            self.delete_post_view_record(post_pk, user_id)

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
