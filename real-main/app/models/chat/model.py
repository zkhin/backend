import logging

import pendulum

from app.mixins.flag.model import FlagModelMixin
from app.mixins.view.model import ViewModelMixin

from .enums import ChatType
from .exceptions import ChatException

logger = logging.getLogger()


class Chat(ViewModelMixin, FlagModelMixin):

    item_type = 'chat'

    def __init__(
        self,
        item,
        dynamo=None,
        member_dynamo=None,
        block_manager=None,
        chat_manager=None,
        chat_message_manager=None,
        user_manager=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        if dynamo:
            self.dynamo = dynamo
        if member_dynamo:
            self.member_dynamo = member_dynamo
        if block_manager:
            self.block_manager = block_manager
        if chat_manager:
            self.chat_manager = chat_manager
        if chat_message_manager:
            self.chat_message_manager = chat_message_manager
        if user_manager:
            self.user_manager = user_manager

        self.item = item
        # immutables
        self.id = item['chatId']
        self.user_id = None  # this model has no 'owner' (required by ViewModelMixin)
        self.type = self.item['chatType']
        self.created_by_user_id = item['createdByUserId']
        self.created_at = pendulum.parse(item['createdAt'])
        self.initial_member_user_ids = item.get('initialMemberUserIds', [])
        self.initial_message_id = item.get('initialMessageId')
        self.initial_message_text = item.get('initialMessageText')

    @property
    def created_by(self):
        if not hasattr(self, '_created_by'):
            self._created_by = self.user_manager.get_user(self.created_by_user_id)
        return self._created_by

    @property
    def messages_count(self):
        return self.item.get('messagesCount', 0)

    @property
    def name(self):
        return self.item.get('name')

    @property
    def user_count(self):
        return self.item.get('userCount', 0)

    def refresh_item(self, strongly_consistent=False):
        self.item = self.dynamo.get(self.id, strongly_consistent=strongly_consistent)
        return self

    def is_member(self, user_id):
        return bool(self.member_dynamo.get(self.id, user_id))

    def edit(self, name=None):
        if self.type != ChatType.GROUP:
            raise ChatException(f'Cannot edit non-GROUP chat `{self.id}`')
        if name is not None:
            self.item = self.dynamo.update_name(self.id, name)
        return self

    def add(self, added_by_user_id, user_ids, now=None):
        now = now or pendulum.now('utc')
        if self.type != ChatType.GROUP:
            raise ChatException(f'Cannot add users to non-GROUP chat `{self.id}`')
        for user_id in set(user_ids):
            warning_prefix = f'User `{added_by_user_id}` cannot add target user `{user_id}` to chat `{self.id}`'
            try:
                self.chat_manager.validate_can_chat(added_by_user_id, user_id)
            except ChatException as err:
                logger.warning(f'{warning_prefix}: {err}')
            else:
                try:
                    self.member_dynamo.add(self.id, user_id, now=now)
                except self.member_dynamo.client.exceptions.ConditionalCheckFailedException:
                    logger.warning(f'{warning_prefix}: target user is already in chat')
        return self

    def leave(self, user_id):
        if self.type != ChatType.GROUP:
            raise ChatException(f'Cannot leave non-GROUP chat `{self.id}`')
        if not self.member_dynamo.delete(self.id, user_id):
            raise ChatException(f'User `{user_id}` is not a member of chat `{self.id}`')
        return self

    def flag(self, user):
        if not self.is_member(user.id):
            raise ChatException(f'User is not part of chat `{self.id}`')

        # write to the db
        self.flag_dynamo.add(self.id, user.id)
        self.item['flagCount'] = self.item.get('flagCount', 0) + 1

        # we don't call super() because that depends on the model having a 'user_id' property
        return self

    def is_crowdsourced_forced_removal_criteria_met(self):
        # force-delete the chat if at least 10% of the members of the chat have flagged it
        flag_count = self.item.get('flagCount', 0)
        user_count = self.item.get('userCount', 0)
        return flag_count > user_count / 10

    def delete(self):
        self.dynamo.delete(self.id)
