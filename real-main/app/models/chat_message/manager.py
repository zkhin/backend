import logging

import pendulum

from app.models import chat, user

from . import exceptions
from .dynamo import ChatMessageDynamo
from .model import ChatMessage

logger = logging.getLogger()


class ChatMessageManager:

    exceptions = exceptions

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['chat_message'] = self
        self.chat_manager = managers.get('chat') or chat.ChatManager(clients, managers=managers)
        self.user_manager = managers.get('user') or user.UserManager(clients, managers=managers)

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = ChatMessageDynamo(clients['dynamo'])

    def get_chat_message(self, message_id, strongly_consistent=False):
        item = self.dynamo.get_chat_message(message_id, strongly_consistent=strongly_consistent)
        return self.init_chat_message(item) if item else None

    def init_chat_message(self, item):
        return ChatMessage(item, self.dynamo) if item else None

    def add_chat_message(self, message_id, text, chat_id, user_id, now=None):
        now = now or pendulum.now('utc')
        text_tags = self.user_manager.get_text_tags(text)

        transacts = [
            self.dynamo.transact_add_chat_message(message_id, chat_id, user_id, text, text_tags, now),
            self.chat_manager.dynamo.transact_register_chat_message_added(chat_id, now),
        ]
        self.dynamo.client.transact_write_items(transacts)

        return self.get_chat_message(message_id, strongly_consistent=True)

    def record_views(self, viewed_by_user_id, message_ids, viewed_at=None):
        viewed_at = viewed_at or pendulum.now('utc')
        for message_id in set(message_ids):
            self.record_view(viewed_by_user_id, message_id, viewed_at)

    def record_view(self, viewed_by_user_id, message_id, viewed_at):
        try:
            self.dynamo.add_chat_message_view(message_id, viewed_by_user_id, viewed_at)
        except exceptions.ChatMessageException as err:
            logger.warning(f'Record view of chat message `{message_id}` by user `{viewed_by_user_id}` failed: {err}')
            return

    def truncate_chat_messages(self, chat_id):
        # delete all chat messages for the chat without bothering to adjust Chat.messageCount
        with self.dynamo.client.table.batch_writer() as batch:
            for item in self.dynamo.generate_chat_messages_by_chat(chat_id):
                key = {'partitionKey': item['partitionKey'], 'sortKey': item['sortKey']}
                batch.delete_item(Key=key)
