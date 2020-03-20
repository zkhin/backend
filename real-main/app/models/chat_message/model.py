import logging

from . import exceptions

logger = logging.getLogger()


class ChatMessage:

    exceptions = exceptions

    def __init__(self, item, chat_message_dynamo, view_manager=None):
        self.dynamo = chat_message_dynamo
        self.item = item
        self.view_manager = view_manager
        # immutables
        self.id = item['messageId']
        self.chat_id = self.item['chatId']
        self.user_id = self.item['userId']

    def refresh_item(self, strongly_consistent=False):
        self.item = self.dynamo.get_chat_message(self.id, strongly_consistent=strongly_consistent)
        return self

    def serialize(self, caller_user_id):
        resp = self.item.copy()
        resp['viewedStatus'] = self.view_manager.get_viewed_status(self, caller_user_id)
        return resp
