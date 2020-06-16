import logging

import pendulum

from app import models
from app.models.card.specs import ChatCardSpec

from . import enums, exceptions
from .dynamo import ChatDynamo, ChatMemberDynamo
from .model import Chat

logger = logging.getLogger()


class ChatManager:

    enums = enums
    exceptions = exceptions

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['chat'] = self
        self.block_manager = managers.get('block') or models.BlockManager(clients, managers=managers)
        self.card_manager = managers.get('card') or models.CardManager(clients, managers=managers)
        self.chat_message_manager = managers.get('chat_message') or models.ChatMessageManager(
            clients, managers=managers
        )
        self.user_manager = managers.get('user') or models.UserManager(clients, managers=managers)

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = ChatDynamo(clients['dynamo'])
            self.member_dynamo = ChatMemberDynamo(clients['dynamo'])

    def get_chat(self, chat_id, strongly_consistent=False):
        item = self.dynamo.get(chat_id, strongly_consistent=strongly_consistent)
        return self.init_chat(item) if item else None

    def get_direct_chat(self, user_id_1, user_id_2):
        item = self.dynamo.get_direct_chat(user_id_1, user_id_2)
        return self.init_chat(item) if item else None

    def init_chat(self, chat_item):
        kwargs = {
            'dynamo': getattr(self, 'dynamo', None),
            'member_dynamo': getattr(self, 'member_dynamo', None),
            'block_manager': self.block_manager,
            'card_manager': self.card_manager,
            'chat_message_manager': self.chat_message_manager,
            'user_manager': self.user_manager,
        }
        return Chat(chat_item, **kwargs) if chat_item else None

    def add_direct_chat(self, chat_id, created_by_user_id, with_user_id, now=None):
        now = now or pendulum.now('utc')

        # can't direct chat with ourselves
        if created_by_user_id == with_user_id:
            raise exceptions.ChatException(f'User `{created_by_user_id}` cannot open direct chat with themselves')

        # can't chat if there's a blocking relationship, either direction
        if self.block_manager.is_blocked(created_by_user_id, with_user_id):
            raise exceptions.ChatException(f'User `{created_by_user_id}` has blocked user `{with_user_id}`')
        if self.block_manager.is_blocked(with_user_id, created_by_user_id):
            raise exceptions.ChatException(f'User `{created_by_user_id}` has been blocked by user `{with_user_id}`')

        # can't add a chat if one already exists between the two users
        if self.get_direct_chat(created_by_user_id, with_user_id):
            raise exceptions.ChatException(
                f'Chat already exists between user `{created_by_user_id}` and user `{with_user_id}`',
            )

        transacts = [
            self.dynamo.transact_add(
                chat_id, enums.ChatType.DIRECT, created_by_user_id, with_user_id=with_user_id, now=now,
            ),
            self.member_dynamo.transact_add(chat_id, created_by_user_id, now=now),
            self.member_dynamo.transact_add(chat_id, with_user_id, now=now),
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

    def add_group_chat(self, chat_id, created_by_user, name=None, now=None):
        now = now or pendulum.now('utc')

        # create the group chat with just caller in it
        transacts = [
            self.dynamo.transact_add(chat_id, enums.ChatType.GROUP, created_by_user.id, name=name, now=now),
            self.member_dynamo.transact_add(chat_id, created_by_user.id, now=now),
            self.user_manager.dynamo.transact_increment_chat_count(created_by_user.id),
        ]
        transact_exceptions = [
            exceptions.ChatException(f'Unable to add chat with id `{chat_id}`... id already used?'),
            exceptions.ChatException(f'Unable to add user `{created_by_user.id}` to chat `{chat_id}`'),
            exceptions.ChatException(f'Unable to increment User.chatCount for user `{created_by_user.id}`'),
        ]
        self.dynamo.client.transact_write_items(transacts, transact_exceptions)

        self.chat_message_manager.add_system_message_group_created(chat_id, created_by_user, name=name, now=now)
        return self.get_chat(chat_id, strongly_consistent=True)

    def leave_all_chats(self, user_id):
        user = None
        for chat_id in self.member_dynamo.generate_chat_ids_by_user(user_id):
            chat = self.get_chat(chat_id)
            if not chat:
                logger.warning(f'Unable to find chat `{chat_id}` that user `{user_id}` is member of, ignoring')
                continue
            if chat.type == enums.ChatType.DIRECT:
                chat.delete_direct_chat()
            else:
                user = user or self.user_manager.get_user(user_id)
                chat.leave(user)

    def postprocess_record(self, pk, sk, old_item, new_item):
        # if this is a member record, check if we went to or from zero unviewed messages
        if sk.startswith('member/'):
            user_id = sk.split('/')[1]
            old_count = int(old_item.get('unviewedMessageCount', {}).get('N', '0')) if old_item else 0
            new_count = int(new_item.get('unviewedMessageCount', {}).get('N', '0')) if new_item else 0
            if old_count == 0 and new_count != 0:
                self.user_manager.dynamo.increment_chats_with_unviewed_messages_count(user_id)
            if old_count != 0 and new_count == 0:
                self.user_manager.dynamo.decrement_chats_with_unviewed_messages_count(user_id, fail_soft=True)

    def postprocess_chat_message_added(self, chat_id, author_user_id, created_at):
        # Note that dynamo has no support for batch updates.
        self.dynamo.update_last_message_activity_at(chat_id, created_at, fail_soft=True)
        self.dynamo.increment_message_count(chat_id)

        # for each memeber of the chat
        #   - update the last message activity timestamp (controls chat ordering)
        #   - for everyone except the author, increment their 'unviewedMessagesCount'
        #     and add a 'You have new chat messages' card if it doesn't already exist
        for user_id in self.member_dynamo.generate_user_ids_by_chat(chat_id):
            self.member_dynamo.update_last_message_activity_at(chat_id, user_id, created_at, fail_soft=True)
            if user_id != author_user_id:
                self.member_dynamo.increment_unviewed_message_count(chat_id, user_id)
                self.card_manager.add_card_by_spec_if_dne(ChatCardSpec(user_id), now=created_at)

    def postprocess_chat_message_deleted(self, chat_id, message_id, author_user_id):
        # Note that dynamo has no support for batch updates.
        self.dynamo.decrement_message_count(chat_id, fail_soft=True)

        # for each memeber of the chat other than the author
        #   - if they've viewed the message, delete the view record
        #   - if they haven't viewed the message, decrement their 'unviewedMessageCount'
        for user_id in self.member_dynamo.generate_user_ids_by_chat(chat_id):
            if user_id != author_user_id:
                resp = self.chat_message_manager.view_dynamo.delete_view(message_id, user_id)
                if not resp:
                    self.member_dynamo.decrement_unviewed_message_count(chat_id, user_id, fail_soft=True)

    def postprocess_chat_message_view_added(self, chat_id, user_id):
        self.member_dynamo.decrement_unviewed_message_count(chat_id, user_id, fail_soft=True)
