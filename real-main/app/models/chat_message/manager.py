import logging

import pendulum
import uuid

from app.models import block, chat, user, view

from . import exceptions
from .dynamo import ChatMessageDynamo
from .model import ChatMessage

logger = logging.getLogger()


class ChatMessageManager:

    exceptions = exceptions

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['chat_message'] = self
        self.block_manager = managers.get('block') or block.BlockManager(clients, managers=managers)
        self.chat_manager = managers.get('chat') or chat.ChatManager(clients, managers=managers)
        self.user_manager = managers.get('user') or user.UserManager(clients, managers=managers)
        self.view_manager = managers.get('view') or view.ViewManager(clients, managers=managers)

        self.clients = clients
        if 'appsync' in clients:
            self.appsync_client = clients['appsync']
        if 'dynamo' in clients:
            self.dynamo = ChatMessageDynamo(clients['dynamo'])

    def get_chat_message(self, message_id, strongly_consistent=False):
        item = self.dynamo.get_chat_message(message_id, strongly_consistent=strongly_consistent)
        return self.init_chat_message(item) if item else None

    def init_chat_message(self, item):
        kwargs = {
            'appsync_client': self.appsync_client,
            'block_manager': self.block_manager,
            'chat_manager': self.chat_manager,
            'user_manager': self.user_manager,
            'view_manager': self.view_manager,
        }
        return ChatMessage(item, self.dynamo, **kwargs)

    def add_chat_message(self, message_id, text, chat_id, user_id, now=None):
        now = now or pendulum.now('utc')
        text_tags = self.user_manager.get_text_tags(text)

        transacts = [
            self.dynamo.transact_add_chat_message(message_id, chat_id, user_id, text, text_tags, now),
            self.chat_manager.dynamo.transact_register_chat_message_added(chat_id, now),
        ]
        self.dynamo.client.transact_write_items(transacts)

        chat = self.chat_manager.get_chat(chat_id)
        chat.update_memberships_last_message_activity_at(now)

        return self.get_chat_message(message_id, strongly_consistent=True)

    def truncate_chat_messages(self, chat_id):
        # delete all chat messages for the chat without bothering to adjust Chat.messageCount
        with self.dynamo.client.table.batch_writer() as batch:
            for chat_message_pk in self.dynamo.generate_chat_messages_by_chat(chat_id, pks_only=True):
                partition_key = chat_message_pk['partitionKey']
                for view_pk in self.view_manager.dynamo.generate_views(partition_key, pks_only=True):
                    batch.delete_item(Key=view_pk)
                batch.delete_item(Key=chat_message_pk)

    def add_system_message_group_created(self, chat_id, created_by_user_id, name=None, now=None):
        user = self.user_manager.get_user(created_by_user_id)
        text = f'@{user.username} created the group'
        if name:
            text += f' "{name}"'
        return self.add_system_message(chat_id, text, user_ids=[created_by_user_id], now=now)

    def add_system_message_added_to_group(self, chat_id, added_by_user_id, users, now=None):
        assert users, 'No system message should be sent if no users added to group'
        user = self.user_manager.get_user(added_by_user_id)
        text = f'@{user.username} added '
        user_1 = users.pop()
        if users:
            text += ', '.join(f'@{u.username}' for u in users)
            text += ' and '
        text += f'@{user_1.username} to the group'
        return self.add_system_message(chat_id, text, user_ids=[u.id for u in users], now=now)

    def add_system_message_left_group(self, chat_id, user_id):
        user = self.user_manager.get_user(user_id)
        text = f'@{user.username} left the group'
        return self.add_system_message(chat_id, text)

    def add_system_message_group_name_edited(self, chat_id, changed_by_user_id, new_name):
        user = self.user_manager.get_user(changed_by_user_id)
        text = f'@{user.username} '
        if new_name:
            text += f'changed the name of the group to "{new_name}"'
        else:
            text += 'deleted the name of the group'
        return self.add_system_message(chat_id, text)

    def add_system_message(self, chat_id, text, user_ids=None, now=None):
        user_id = None
        message_id = str(uuid.uuid4())
        message = self.add_chat_message(message_id, text, chat_id, user_id, now=now)
        message.trigger_notifications(message.enums.ChatMessageNotificationType.ADDED, user_ids=user_ids)
        return message
