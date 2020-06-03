import logging

import gql

logger = logging.getLogger()


class CardAppSync:
    def __init__(self, appsync_client):
        self.client = appsync_client

    def trigger_notification(self, notification_type, card):
        mutation = gql.gql(
            '''
            mutation TriggerCardNotification ($input: CardNotificationInput!) {
                triggerCardNotification (input: $input) {
                    userId
                    type
                    card {
                        cardId
                        title
                        subTitle
                        action
                    }
                }
            }
        '''
        )
        input_obj = {
            'userId': card.user_id,
            'type': notification_type,
            'cardId': card.id,
            'title': card.item['title'],
            'subTitle': card.item.get('subTitle'),
            'action': card.item['action'],
        }
        self.client.send(mutation, {'input': input_obj})
