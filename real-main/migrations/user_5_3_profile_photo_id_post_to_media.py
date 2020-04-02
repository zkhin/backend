import logging
import os

import boto3

DYNAMO_TABLE = os.environ.get('DYNAMO_TABLE')

logger = logging.getLogger()


class Migration:
    """
    Move User.photoMediaId to User.photoPostId, making a best-effort attempt
    to translate mediaId's to photoId's, and falling back on re-using a mediaId
    as a photoId when the media is not found.
    """

    def __init__(self, boto_table):
        self.boto_table = boto_table

    def run(self):
        for user_item in self.generate_all_users_with_photo_media_ids():
            self.migrate_user(user_item)

    def generate_all_users_with_photo_media_ids(self):
        "Return a generator of all items that need to be migrated"
        scan_kwargs = {
            'FilterExpression': 'begins_with(partitionKey, :pk_prefix) AND attribute_exists(photoMediaId)',
            'ExpressionAttributeValues': {
                ':pk_prefix': 'user/',
            },
        }
        while True:
            paginated = self.boto_table.scan(**scan_kwargs)
            for item in paginated['Items']:
                yield item
            if 'LastEvaluatedKey' not in paginated:
                break
            scan_kwargs['ExclusiveStartKey'] = paginated['LastEvaluatedKey']

    def migrate_user(self, user_item):
        user_id = user_item['userId']
        logger.warning(f'Migrating `{user_id}`')

        # try to pull the media object from dynamo to get the post id
        media_id = user_item['photoMediaId']
        kwargs = {
            'Key': {
                'partitionKey': f'media/{media_id}',
                'sortKey': '-',
            },
        }
        media_item = self.boto_table.get_item(**kwargs).get('Item')

        kwargs = {
            'Key': {
                'partitionKey': user_item['partitionKey'],
                'sortKey': user_item['sortKey'],
            },
            'UpdateExpression': 'REMOVE photoMediaId',
            'ExpressionAttributeValues': {
                ':mid': media_id,
            },
            'ConditionExpression': 'attribute_exists(partitionKey) AND photoMediaId = :mid',
        }

        if media_item:
            kwargs['UpdateExpression'] += ' SET photoPostId = :pid'
            kwargs['ExpressionAttributeValues'][':pid'] = media_item['postId']
        else:
            logger.warning(f'Migrating `{user_id}`: media `{media_id}` does not exist, using mediaId as postId')
            kwargs['UpdateExpression'] += ' SET photoPostId = :mid'

        self.boto_table.update_item(**kwargs)


if __name__ == '__main__':
    assert DYNAMO_TABLE, 'Must set env variable DYNAMO_TABLE to dynamo table name'
    boto_table = boto3.resource('dynamodb').Table(DYNAMO_TABLE)
    migration = Migration(boto_table)
    migration.run()
