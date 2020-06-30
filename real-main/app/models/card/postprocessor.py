import logging

from .enums import CardNotificationType

logger = logging.getLogger()


class CardPostProcessor:
    def __init__(self, appsync=None, user_manager=None):
        self.appsync = appsync
        self.user_manager = user_manager

    def run(self, pk, sk, old_item, new_item):
        if sk == '-':
            self.adjust_user_card_count(old_item, new_item)
            self.send_gql_notifications(old_item, new_item)

    def adjust_user_card_count(self, old_item, new_item):
        user_id = (new_item or old_item)['gsiA1PartitionKey'].split('/')[1]
        if new_item and not old_item:
            self.user_manager.dynamo.increment_card_count(user_id)
        if not new_item and old_item:
            self.user_manager.dynamo.decrement_card_count(user_id, fail_soft=True)

    def send_gql_notifications(self, old_item, new_item):
        user_id = (new_item or old_item)['gsiA1PartitionKey'].split('/')[1]
        card_id = (new_item or old_item)['partitionKey'].split('/')[1]
        title = (new_item or old_item)['title']
        action = (new_item or old_item)['action']
        sub_title = (new_item or old_item).get('subTitle')
        if new_item and not old_item:
            self.appsync.trigger_notification(
                CardNotificationType.ADDED, user_id, card_id, title, action, sub_title=sub_title
            )
        if not new_item and old_item:
            self.appsync.trigger_notification(
                CardNotificationType.DELETED, user_id, card_id, title, action, sub_title=sub_title,
            )
