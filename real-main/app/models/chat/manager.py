import collections
import logging

import pendulum

from app import models
from app.mixins.base import ManagerBase
from app.mixins.view.manager import ViewManagerMixin

from . import enums, exceptions
from .dynamo import ChatDynamo, ChatMemberDynamo
from .model import Chat
from .postprocessor import ChatPostProcessor

logger = logging.getLogger()


class ChatManager(ViewManagerMixin, ManagerBase):

    enums = enums
    exceptions = exceptions
    item_type = 'chat'

    def __init__(self, clients, managers=None):
        super().__init__(clients, managers=managers)
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

    @property
    def postprocessor(self):
        if not hasattr(self, '_postprocessor'):
            self._postprocessor = ChatPostProcessor(
                dynamo=getattr(self, 'dynamo', None),
                member_dynamo=getattr(self, 'member_dynamo', None),
                view_dynamo=getattr(self, 'view_dynamo', None),
                card_manager=self.card_manager,
                chat_message_manager=self.chat_message_manager,
                user_manager=self.user_manager,
            )
        return self._postprocessor

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
            'view_dynamo': getattr(self, 'view_dynamo', None),
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

    def record_views(self, chat_ids, user_id, viewed_at=None):
        for chat_id, view_count in dict(collections.Counter(chat_ids)).items():
            chat = self.get_chat(chat_id)
            if not chat:
                logger.warning(f'Cannot record view(s) by user `{user_id}` on DNE chat `{chat_id}`')
            elif not chat.is_member(user_id):
                logger.warning(f'Cannot record view(s) by non-member user `{user_id}` on chat `{chat_id}`')
            else:
                chat.record_view_count(user_id, view_count, viewed_at=viewed_at)
