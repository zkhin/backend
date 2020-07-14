import logging

logger = logging.getLogger()


class ChatMessagePostProcessor:
    def __init__(self, dynamo=None, manager=None, chat_manager=None):
        self.dynamo = dynamo
        self.manager = manager
        self.chat_manager = chat_manager

    def run(self, pk, sk, old_item, new_item):
        message_id = pk.split('/')[1]

        if sk == '-':
            if new_item:
                self.manager.init_chat_message(new_item).on_add_or_edit(old_item)
            else:
                self.manager.init_chat_message(old_item).on_delete()

        # could try to consolidate this in a FlagPostProcessor
        if sk.startswith('flag/'):
            user_id = sk.split('/')[1]
            if not old_item and new_item:
                self.manager.on_flag_added(message_id, user_id)
            if old_item and not new_item:
                self.manager.on_flag_deleted(message_id)
