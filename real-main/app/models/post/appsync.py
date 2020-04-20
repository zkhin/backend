import logging

logger = logging.getLogger()


class PostAppSync:

    def __init__(self, appsync_client):
        self.client = appsync_client

    def trigger_notification(self, notification_type, post):
        mutation = '''
            mutation TriggerPostNotification ($input: PostNotificationInput!) {
                triggerPostNotification (input: $input) {
                    userId
                    type
                    post {
                        postId
                        postStatus
                        isVerified
                    }
                }
            }
        '''
        input_obj = {
            'userId': post.user_id,
            'type': notification_type,
            'postId': post.id,
            'postStatus': post.status,
            # TODO: remove the reference to post.media here after isVerified is migrated from media to post
            'isVerified': post.item.get('isVerified', post.media.item.get('isVerified') if post.media else None),
        }
        self.client.send(mutation, {'input': input_obj})
