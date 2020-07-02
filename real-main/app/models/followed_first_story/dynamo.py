import logging

logger = logging.getLogger()


class FollowedFirstStoryDynamo:
    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def set_all(self, follower_user_ids_generator, post_item):
        "Set the given post as our followed first story for all our followers"
        posted_by_user_id = post_item['postedByUserId']
        with self.client.table.batch_writer() as batch:
            for follower_user_id in follower_user_ids_generator:
                item = {
                    'schemaVersion': 1,
                    'partitionKey': f'user/{posted_by_user_id}',
                    'sortKey': f'follower/{follower_user_id}/firstStory',
                    'gsiA2PartitionKey': f'follower/{follower_user_id}/firstStory',
                    'gsiA2SortKey': post_item['expiresAt'],
                    'postId': post_item['postId'],
                }
                batch.put_item(item)

    def delete_all(self, follower_user_ids_generator, posted_by_user_id):
        "Delete our followed first story from all our followers"
        with self.client.table.batch_writer() as batch:
            for follower_user_id in follower_user_ids_generator:
                batch.delete_item(
                    Key={
                        'partitionKey': f'user/{posted_by_user_id}',
                        'sortKey': f'follower/{follower_user_id}/firstStory',
                    }
                )
