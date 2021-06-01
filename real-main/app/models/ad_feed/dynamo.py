import logging

import pendulum

logger = logging.getLogger()


class AdFeedDynamo:
    def __init__(self, dynamo_ad_feed_client):
        self.client = dynamo_ad_feed_client

    def key(self, post_id, user_id):
        return {
            'postId': post_id,
            'userId': user_id,
        }

    def new_item(self, post_id, user_id):
        return {
            **self.key(post_id, user_id),
            'lastViewedAt': '!',
        }

    def get(self, post_id, user_id):
        return self.client.get_item(self.key(post_id, user_id))

    def add_ad_post_for_users(self, post_id, user_id_generator):
        item_generator = (self.new_item(post_id, user_id) for user_id in user_id_generator)
        self.client.batch_put_items(item_generator)

    def add_ad_posts_for_user(self, user_id, post_id_generator):
        item_generator = (self.new_item(post_id, user_id) for post_id in post_id_generator)
        self.client.batch_put_items(item_generator)

    def set_last_viewed_at(self, post_id, user_id, lastViewedAtStr):
        query_kwargs = {
            'Key': self.key(post_id, user_id),
            'UpdateExpression': 'SET lastViewedAt = :lva',
            'ExpressionAttributeValues': {':lva': lastViewedAtStr},
        }
        return self.client.update_item(query_kwargs)

    def record_payment_start(self, post_id, user_id, newLastPaymentForViewAt, oldLastPaymentForViewAt):
        query_kwargs = {
            'Key': self.key(post_id, user_id),
            'UpdateExpression': 'SET lastPaymentForViewAt = :nlpfva',
            'ExpressionAttributeValues': {':nlpfva': newLastPaymentForViewAt.to_iso8601_string()},
        }
        if oldLastPaymentForViewAt:
            query_kwargs['ConditionExpression'] = 'lastPaymentForViewAt = :olpfva'
            query_kwargs['ExpressionAttributeValues'][':olpfva'] = oldLastPaymentForViewAt.to_iso8601_string()
        else:
            query_kwargs['ConditionExpression'] = 'attribute_not_exists(lastPaymentForViewAt)'
        return self.client.update_item(query_kwargs)

    def record_payment_finish(self, post_id, user_id, now=None):
        now = now or pendulum.now('utc')
        query_kwargs = {
            'Key': self.key(post_id, user_id),
            'UpdateExpression': 'ADD paymentCount :one SET lastPaymentFinishedAt = :lpfa',
            'ExpressionAttributeValues': {
                ':one': 1,
                ':lpfa': now.to_iso8601_string(),
            },
        }
        return self.client.update_item(query_kwargs)

    def delete_by_post(self, post_id):
        key_generator = self.generate_keys_by_post(post_id)
        self.client.batch_delete(key_generator)

    def delete_by_user(self, user_id):
        key_generator = self.generate_keys_by_user(user_id)
        self.client.batch_delete(key_generator)

    def generate_keys_by_post(self, post_id):
        query_kwargs = {
            'KeyConditionExpression': 'postId = :pid',
            'ExpressionAttributeValues': {':pid': post_id},
            'ProjectionExpression': 'postId, userId',
        }
        return self.client.generate_all_query(query_kwargs)

    def generate_keys_by_user(self, user_id):
        query_kwargs = {
            'KeyConditionExpression': 'userId = :uid',
            'ExpressionAttributeValues': {':uid': user_id},
            'IndexName': 'GSI-A1',
            'ProjectionExpression': 'postId, userId',
        }
        return self.client.generate_all_query(query_kwargs)
