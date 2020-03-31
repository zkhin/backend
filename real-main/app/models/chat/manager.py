import logging

import pendulum

from app.models import block, chat_message, user

from . import enums, exceptions
from .dynamo import ChatDynamo
from .model import Chat

logger = logging.getLogger()


class ChatManager:

    enums = enums
    exceptions = exceptions

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['chat'] = self
        self.block_manager = managers.get('block') or block.BlockManager(clients, managers=managers)
        self.chat_message_manager = (
            managers.get('chat_message')
            or chat_message.ChatMessageManager(clients, managers=managers)
        )
        self.user_manager = managers.get('user') or user.UserManager(clients, managers=managers)

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = ChatDynamo(clients['dynamo'])

    def get_chat(self, chat_id, strongly_consistent=False):
        item = self.dynamo.get_chat(chat_id, strongly_consistent=strongly_consistent)
        return self.init_chat(item) if item else None

    def get_direct_chat(self, user_id_1, user_id_2):
        item = self.dynamo.get_direct_chat(user_id_1, user_id_2)
        return self.init_chat(item) if item else None

    def init_chat(self, chat_item):
        kwargs = {
            'block_manager': self.block_manager,
            'chat_message_manager': self.chat_message_manager,
            'user_manager': self.user_manager,
        }
        return Chat(chat_item, self.dynamo, **kwargs) if chat_item else None

    def add_direct_chat(self, chat_id, created_by_user_id, with_user_id, now=None):
        now = now or pendulum.now('utc')

        # can't direct chat with ourselves
        if created_by_user_id == with_user_id:
            raise exceptions.ChatException(f'User `{created_by_user_id}` cannot open direct chat with themselves')

        # can't chat if there's a blocking relationship, either direction
        if self.block_manager.is_blocked(created_by_user_id, with_user_id):
            raise exceptions.ChatException(f'User `{created_by_user_id}` has blocked user `{with_user_id}`')
        if self.block_manager.is_blocked(with_user_id, created_by_user_id):
            raise exceptions.ChatException(f'User `{with_user_id}` has blocked user `{created_by_user_id}`')

        # can't add a chat if one already exists between the two users
        if self.get_direct_chat(created_by_user_id, with_user_id):
            raise exceptions.ChatException(
                f'Chat already exists between user `{created_by_user_id}` and user `{with_user_id}`',
            )

        transacts = [
            self.dynamo.transact_add_chat(
                chat_id, enums.ChatType.DIRECT, created_by_user_id, with_user_id=with_user_id, now=now,
            ),
            self.dynamo.transact_add_chat_membership(chat_id, created_by_user_id, now=now),
            self.dynamo.transact_add_chat_membership(chat_id, with_user_id, now=now),
            self.user_manager.dynamo.transact_increment_chat_count(created_by_user_id),
            self.user_manager.dynamo.transact_increment_chat_count(with_user_id),
        ]
        transact_exceptions = [
            exceptions.ChatException(f'Unable to add chat with id `{chat_id}`... id already used?'),
            exceptions.ChatException(f'Unable to add user `{created_by_user_id}` to chat `{chat_id}`'),
            exceptions.ChatException(f'Unable to add user `{with_user_id}` to chat `{chat_id}`'),
            exceptions.ChatException(f'Unable to increment User.chatCount for user `{created_by_user_id}`'),
            exceptions.ChatException(f'Unable to increment User.chatCount for user `{with_user_id}`'),
        ]
        self.dynamo.client.transact_write_items(transacts, transact_exceptions)

        return self.get_chat(chat_id, strongly_consistent=True)

    def add_group_chat(self, chat_id, created_by_user_id, name=None, now=None):
        now = now or pendulum.now('utc')

        # create the group chat with just caller in it
        transacts = [
            self.dynamo.transact_add_chat(chat_id, enums.ChatType.GROUP, created_by_user_id, name=name, now=now),
            self.dynamo.transact_add_chat_membership(chat_id, created_by_user_id, now=now),
            self.user_manager.dynamo.transact_increment_chat_count(created_by_user_id),
        ]
        transact_exceptions = [
            exceptions.ChatException(f'Unable to add chat with id `{chat_id}`... id already used?'),
            exceptions.ChatException(f'Unable to add user `{created_by_user_id}` to chat `{chat_id}`'),
            exceptions.ChatException(f'Unable to increment User.chatCount for user `{created_by_user_id}`'),
        ]
        self.dynamo.client.transact_write_items(transacts, transact_exceptions)

        self.chat_message_manager.add_system_message_group_created(chat_id, created_by_user_id, name=name, now=now)
        return self.get_chat(chat_id, strongly_consistent=True)

    def leave_all_chats(self, user_id):
        for chat_id in self.dynamo.generate_chat_membership_chat_ids_by_user(user_id):
            chat = self.get_chat(chat_id)
            if not chat:
                logger.warning(f'Unable to find chat `{chat_id}` that user `{user_id}` is member of, ignoring')
                continue
            if chat.type == enums.ChatType.DIRECT:
                chat.delete_direct_chat()
            else:
                chat.leave(user_id)
