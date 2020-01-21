import logging

logger = logging.getLogger()


class FollowedFirstStoryDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def set_all(self, follower_user_ids, post):
        "Set the given post as our followed first story for all our followers"
        assert len(follower_user_ids) <= 25, 'Dynamo batch writer cannot handle more than 25 writes at a time'
        with self.client.table.batch_writer() as batch:
            for follower_user_id in follower_user_ids:
                item = {
                    'schemaVersion': 1,
                    'partitionKey': f'followedFirstStory/{follower_user_id}/{post["postedByUserId"]}',
                    'sortKey': '-',
                    'gsiA1PartitionKey': f'followedFirstStory/{follower_user_id}',
                    'gsiA1SortKey': post['expiresAt'],
                    'postedByUserId': post['postedByUserId'],
                    'postId': post['postId'],
                    'postedAt': post['postedAt'],
                    'expiresAt': post['expiresAt'],
                }
                batch.put_item(item)

    def delete_all(self, follower_user_ids, posted_by_user_id):
        "Delete our followed first story from all our followers"
        assert len(follower_user_ids) <= 25, 'Dynamo batch writer cannot handle more than 25 writes at a time'
        with self.client.table.batch_writer() as batch:
            for follower_user_id in follower_user_ids:
                pk = {
                    'partitionKey': f'followedFirstStory/{follower_user_id}/{posted_by_user_id}',
                    'sortKey': '-'
                }
                batch.delete_item(Key=pk)
