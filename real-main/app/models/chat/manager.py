import collections
import logging

import pendulum

from app import models
from app.mixins.base import ManagerBase
from app.mixins.flag.manager import FlagManagerMixin
from app.mixins.view.manager import ViewManagerMixin
from app.models.user.enums import UserStatus

from .dynamo import ChatDynamo, ChatMemberDynamo
from .enums import ChatType
from .exceptions import ChatException
from .model import Chat

logger = logging.getLogger()


class ChatManager(FlagManagerMixin, ViewManagerMixin, ManagerBase):

    item_type = 'chat'

    def __init__(self, clients, managers=None):
        super().__init__(clients, managers=managers)
        managers = managers or {}
        managers['chat'] = self
        self.block_manager = managers.get('block') or models.BlockManager(clients, managers=managers)
        self.chat_message_manager = managers.get('chat_message') or models.ChatMessageManager(
            clients, managers=managers
        )
        self.user_manager = managers.get('user') or models.UserManager(clients, managers=managers)

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = ChatDynamo(clients['dynamo'])
            self.member_dynamo = ChatMemberDynamo(clients['dynamo'])
        if 'real_dating' in clients:
            self.real_dating_client = clients['real_dating']

    def get_model(self, item_id, strongly_consistent=False):
        return self.get_chat(item_id, strongly_consistent=strongly_consistent)

    def get_chat(self, chat_id, strongly_consistent=False):
        item = self.dynamo.get(chat_id, strongly_consistent=strongly_consistent)
        return self.init_chat(item) if item else None

    def get_direct_chat(self, user_id_1, user_id_2):
        item = self.dynamo.get_direct_chat(user_id_1, user_id_2)
        return self.init_chat(item) if item else None

    def init_chat(self, chat_item):
        kwargs = {
            'dynamo': getattr(self, 'dynamo', None),
            'flag_dynamo': getattr(self, 'flag_dynamo', None),
            'member_dynamo': getattr(self, 'member_dynamo', None),
            'view_dynamo': getattr(self, 'view_dynamo', None),
            'block_manager': self.block_manager,
            'chat_manager': self,
            'chat_message_manager': self.chat_message_manager,
            'user_manager': self.user_manager,
        }
        return Chat(chat_item, **kwargs) if chat_item else None

    def add_direct_chat(
        self,
        chat_id,
        user_id,
        with_user_id,
        initial_message_id=None,
        initial_message_text=None,
        now=None,
    ):
        # initial_message_text will be treated as a system-generated message if there's no initial_message_id
        if initial_message_id:
            assert initial_message_text
        now = now or pendulum.now('utc')

        self.validate_can_chat(user_id, with_user_id)
        if self.get_direct_chat(user_id, with_user_id):
            raise ChatException(f'Chat already exists between user `{user_id}` and user `{with_user_id}`')

        chat_item = self.dynamo.add(
            chat_id,
            ChatType.DIRECT,
            user_id,
            with_user_ids=[with_user_id],
            initial_message_id=initial_message_id,
            initial_message_text=initial_message_text,
            now=now,
        )
        return self.init_chat(chat_item)

    def add_group_chat(
        self,
        chat_id,
        user_id,
        with_user_ids,
        initial_message_id=None,
        initial_message_text=None,
        name=None,
        now=None,
    ):
        # initial_message_text will be treated as a system-generated message if there's no initial_message_id
        if initial_message_id:
            assert initial_message_text
        now = now or pendulum.now('utc')
        validated_with_user_ids = []
        for with_user_id in with_user_ids:
            try:
                self.validate_can_chat(user_id, with_user_id)
            except ChatException as err:
                logger.warning(f'Not adding user `{with_user_id}` to chat `{chat_id}`: {err}')
            else:
                validated_with_user_ids.append(with_user_id)
        chat_item = self.dynamo.add(
            chat_id,
            ChatType.GROUP,
            user_id,
            with_user_ids=validated_with_user_ids,
            initial_message_id=initial_message_id,
            initial_message_text=initial_message_text,
            name=name,
            now=now,
        )
        return self.init_chat(chat_item)

    def on_user_delete_leave_all_chats(self, user_id, old_item):
        for chat_id in self.member_dynamo.generate_chat_ids_by_user(user_id):
            chat = self.get_chat(chat_id)
            if not chat:
                logger.warning(f'Unable to find chat `{chat_id}` that user `{user_id}` is member of, ignoring')
                continue
            if chat.type == ChatType.DIRECT:
                chat.delete()
            else:
                chat.leave(user_id)

    def record_views(self, chat_ids, user_id, viewed_at=None):
        for chat_id, view_count in dict(collections.Counter(chat_ids)).items():
            chat = self.get_chat(chat_id)
            if not chat:
                logger.warning(f'Cannot record view(s) by user `{user_id}` on DNE chat `{chat_id}`')
            elif not chat.is_member(user_id):
                logger.warning(f'Cannot record view(s) by non-member user `{user_id}` on chat `{chat_id}`')
            else:
                chat.record_view_count(user_id, view_count, viewed_at=viewed_at)

    def on_chat_add(self, chat_id, new_item):
        chat = self.init_chat(new_item)
        # create chat/member items, return them so unit tests can more easily simulate dynamo stream processor
        return [
            self.member_dynamo.add(chat_id, user_id, now=chat.created_at)
            for user_id in chat.initial_member_user_ids
        ]

    def on_chat_user_count_change(self, chat_id, new_item, old_item):
        old_chat = self.init_chat(old_item)
        new_chat = self.init_chat(new_item)
        assert old_chat.user_count != new_chat.user_count, 'Should only be called when userCount changes'
        if new_chat.user_count < 1:
            new_chat.delete()

    def on_chat_member_add(self, chat_id, new_item):
        self.dynamo.increment_user_count(chat_id)

    def on_chat_member_delete(self, chat_id, old_item):
        self.dynamo.decrement_user_count(chat_id)

    def on_chat_message_add(self, message_id, new_item):
        message = self.chat_message_manager.init_chat_message(new_item)
        self.dynamo.update_last_message_activity_at(message.chat_id, message.created_at)
        self.dynamo.increment_messages_count(message.chat_id)

        # for each memeber of the chat
        #   - update the last message activity timestamp (controls chat ordering)
        #   - for everyone except the author, increment their 'messagesUnviewedCount'
        for user_id in self.member_dynamo.generate_user_ids_by_chat(message.chat_id):
            self.member_dynamo.update_last_message_activity_at(message.chat_id, user_id, message.created_at)
            if user_id != message.user_id:
                # Note that dynamo has no support for batch updates.
                self.member_dynamo.increment_messages_unviewed_count(message.chat_id, user_id)
                # TODO
                # we can be in a state where the user manually dismissed a card, and this view does not
                # change the user's overall count of chats with unread messages, but should still create a card

    def on_chat_message_delete(self, message_id, old_item):
        message = self.chat_message_manager.init_chat_message(old_item)
        self.dynamo.decrement_messages_count(message.chat_id)

        # for each memeber of the chat other than the author
        #   - delete any view record that exists directly on the message
        #   - determine if the message had status 'unviewed', and if so, then decrement the unviewed message counter
        for user_id in self.member_dynamo.generate_user_ids_by_chat(message.chat_id):
            if user_id != message.user_id:
                chat_view_item = self.view_dynamo.get_view(message.chat_id, user_id)
                chat_last_viewed_at = pendulum.parse(chat_view_item['lastViewedAt']) if chat_view_item else None
                if not (chat_last_viewed_at and chat_last_viewed_at > message.created_at):
                    # Note that dynamo has no support for batch updates.
                    self.member_dynamo.decrement_messages_unviewed_count(message.chat_id, user_id)

    def sync_member_messages_unviewed_count(self, chat_id, new_item, old_item=None):
        if new_item.get('viewCount', 0) > (old_item or {}).get('viewCount', 0):
            user_id = new_item['sortKey'].split('/')[1]
            self.member_dynamo.clear_messages_unviewed_count(chat_id, user_id)

    def on_flag_add(self, chat_id, new_item):
        chat_item = self.dynamo.increment_flag_count(chat_id)
        chat = self.init_chat(chat_item)

        # force delete the chat_message?
        if chat.is_crowdsourced_forced_removal_criteria_met():
            logger.warning(f'Force deleting chat `{chat_id}` from flagging')
            chat.delete()

    def on_chat_message_flag_add(self, message_id, new_item):
        user_id = new_item['sortKey'].split('/')[1]
        chat = self.chat_message_manager.get_chat_message(message_id).chat
        user_count = chat.item.get('userCount', 0)
        # if a flag for that user already exists on the chat
        if chat.flag_dynamo.get(chat.id, user_id) and user_count == 2:
            # force delete chat
            chat.delete(forced=True)
            return

        # add flag to chat
        user = self.user_manager.get_user(user_id)
        chat.flag(user)

    def on_chat_delete_delete_memberships(self, chat_id, old_item):
        for user_id in self.member_dynamo.generate_user_ids_by_chat(chat_id):
            self.member_dynamo.delete(chat_id, user_id)

    def validate_can_chat(self, user_id_1, user_id_2):
        if user_id_1 == user_id_2:
            raise ChatException(f'User `{user_id_1}` cannot chat with themselves')

        if self.block_manager.is_blocked(user_id_1, user_id_2):
            raise ChatException(f'User `{user_id_1}` has blocked user `{user_id_2}`')

        if self.block_manager.is_blocked(user_id_2, user_id_1):
            raise ChatException(f'User `{user_id_2}` has been blocked by `{user_id_1}`')

        user2 = self.user_manager.get_user(user_id_2)
        if not user2:
            raise ChatException(f'User `{user_id_2}` does not exist')

        if user2.status != UserStatus.ACTIVE:
            raise ChatException(f'User `{user_id_2}` has non-active status `{user2.status}`')

        if not self.real_dating_client.can_contact(user_id_1, user_id_2):
            raise ChatException('Users `{user_id_1}` and `{user_id_2}` prohibited from chatting due to dating')
