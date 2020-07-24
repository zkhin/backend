import logging

logger = logging.getLogger()


class FirstStoryDynamo:
    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def set_all(self, follower_user_ids_generator, post_item):
        "Set the given post as our followed first story for all our followers"
        posted_by_user_id = post_item['postedByUserId']
        item_generator = (
            {
                'schemaVersion': 1,
                'partitionKey': f'user/{posted_by_user_id}',
                'sortKey': f'follower/{follower_user_id}/firstStory',
                'gsiA2PartitionKey': f'follower/{follower_user_id}/firstStory',
                'gsiA2SortKey': post_item['expiresAt'],
                'postId': post_item['postId'],
            }
            for follower_user_id in follower_user_ids_generator
        )
        self.client.batch_put_items(item_generator)

    def delete_all(self, follower_user_ids_generator, posted_by_user_id):
        "Delete our followed first story from all our followers"
        keys_generator = (
            {'partitionKey': f'user/{posted_by_user_id}', 'sortKey': f'follower/{follower_user_id}/firstStory'}
            for follower_user_id in follower_user_ids_generator
        )
        self.client.batch_delete_items(keys_generator)
