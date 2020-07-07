import logging

import pendulum

logger = logging.getLogger()


class ChatMessagePostProcessor:
    def __init__(self, dynamo=None, chat_manager=None):
        self.dynamo = dynamo
        self.chat_manager = chat_manager

    def run(self, pk, sk, old_item, new_item):
        message_id = pk.split('/')[1]

        if sk == '-':
            chat_id = (new_item or old_item)['chatId']
            user_id = (new_item or old_item).get('userId')  # system messages have no userId
            created_at = pendulum.parse((new_item or old_item)['createdAt'])

            # message added
            if not old_item and new_item:
                self.chat_manager.postprocessor.chat_message_added(chat_id, user_id, created_at)

            # message deleted
            if old_item and not new_item:
                self.chat_manager.postprocessor.chat_message_deleted(chat_id, message_id, user_id, created_at)

        # message view added
        if sk.startswith('view/') and not old_item and new_item:
            user_id = sk.split('/')[1]
            message_item = self.dynamo.get_chat_message(message_id)
            self.chat_manager.postprocessor.chat_message_view_added(message_item['chatId'], user_id)

        # could try to consolidate this in a FlagPostProcessor
        if sk.startswith('flag/'):
            user_id = sk.split('/')[1]
            if not old_item and new_item:
                self.message_flag_added(message_id, user_id)
            if old_item and not new_item:
                self.message_flag_deleted(message_id)

    def message_flag_added(self, message_id, user_id):
        self.dynamo.increment_flag_count(message_id)

    def message_flag_deleted(self, message_id):
        self.dynamo.decrement_flag_count(message_id, fail_soft=True)
