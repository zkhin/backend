import logging

import pendulum

from app.models.card.specs import ChatCardSpec

from . import enums, exceptions

logger = logging.getLogger()


class Chat:

    enums = enums
    exceptions = exceptions

    def __init__(
        self,
        item,
        dynamo=None,
        member_dynamo=None,
        block_manager=None,
        card_manager=None,
        chat_message_manager=None,
        user_manager=None,
    ):
        if dynamo:
            self.dynamo = dynamo
        if member_dynamo:
            self.member_dynamo = member_dynamo
        if block_manager:
            self.block_manager = block_manager
        if card_manager:
            self.card_manager = card_manager
        if chat_message_manager:
            self.chat_message_manager = chat_message_manager
        if user_manager:
            self.user_manager = user_manager

        self.item = item
        # immutables
        self.id = item['chatId']
        self.type = self.item['chatType']
        self.created_by_user_id = item['createdByUserId']

    def refresh_item(self, strongly_consistent=False):
        self.item = self.dynamo.get(self.id, strongly_consistent=strongly_consistent)
        return self

    def is_member(self, user_id):
        return bool(self.member_dynamo.get(self.id, user_id))

    def edit(self, edited_by_user, name=None):
        if self.type != enums.ChatType.GROUP:
            raise exceptions.ChatException(f'Cannot edit non-GROUP chat `{self.id}`')

        if name is None:
            return
        self.item = self.dynamo.update_name(self.id, name)
        self.chat_message_manager.add_system_message_group_name_edited(self.id, edited_by_user, name)
        self.item['messageCount'] = self.item.get('messageCount', 0) + 1
        return self

    def add(self, added_by_user, user_ids, now=None):
        now = now or pendulum.now('utc')
        if self.type != enums.ChatType.GROUP:
            raise exceptions.ChatException(f'Cannot add users to non-GROUP chat `{self.id}`')

        users = []
        for user_id in set(user_ids):

            # make sure the user exists
            user = self.user_manager.get_user(user_id)
            if not user:
                continue

            if added_by_user.id is not None:
                if user_id == added_by_user.id:
                    continue  # must already be in the chat

                if self.block_manager.is_blocked(added_by_user.id, user_id):
                    continue  # can't add a user you're blocking

                if self.block_manager.is_blocked(user_id, added_by_user.id):
                    continue  # can't add a user who is blocking you

            transacts = [
                self.member_dynamo.transact_add(self.id, user_id, now=now),
                self.dynamo.transact_increment_user_count(self.id),
                self.user_manager.dynamo.transact_increment_chat_count(user_id),
            ]
            transact_exceptions = [
                exceptions.ChatException(f'Unable to add chat membership of user `{user_id} in chat `{self.id}`'),
                Exception(f'Unable to increment Chat.userCount for chat `{self.id}`'),
                Exception(f'Unable to increment User.chatCount for chat `{user_id}`'),
            ]
            try:
                self.dynamo.client.transact_write_items(transacts, transact_exceptions)
            except exceptions.ChatException:
                # user is already in the chat, nothing to do
                pass
            else:
                self.item['userCount'] = self.item.get('userCount', 0) + 1
                users.append(user)

        if users:
            self.chat_message_manager.add_system_message_added_to_group(self.id, added_by_user, users, now=now)
            self.item['messageCount'] = self.item.get('messageCount', 0) + 1

    def update_last_message_activity_at(self, activity_by_user_id, now):
        # Note that dynamo has no support for batch updates.
        # This update will need to be made async at some scale (chats with 1000+ members?)
        resp = self.dynamo.update_last_message_activity_at(self.id, now, fail_soft=True)
        if resp:
            self.item = resp
        for user_id in self.member_dynamo.generate_user_ids_by_chat(self.id):
            self.member_dynamo.update_last_message_activity_at(self.id, user_id, now, fail_soft=True)
            if user_id != activity_by_user_id:
                self.card_manager.add_card_by_spec_if_dne(ChatCardSpec(user_id), now=now)

    def leave(self, user):
        if self.type != enums.ChatType.GROUP:
            raise exceptions.ChatException(f'Cannot leave non-GROUP chat `{self.id}`')

        # leave the chat
        transacts = [
            self.member_dynamo.transact_delete(self.id, user.id),
            self.dynamo.transact_decrement_user_count(self.id),
            self.user_manager.dynamo.transact_decrement_chat_count(user.id),
        ]
        transact_exceptions = [
            exceptions.ChatException(f'Unable to delete chat membership of user `{user.id}` in chat `{self.id}`'),
            Exception(f'Unable to decrement Chat.userCount for chat `{self.id}`'),
            Exception(f'Unable to decrement User.chatCount for chat `{user.id}`'),
        ]
        self.dynamo.client.transact_write_items(transacts, transact_exceptions)
        self.item['userCount'] -= 1

        # were we the last user in the chat? If so, clean up
        if self.item['userCount'] <= 0:
            self.delete_group_chat()
        else:
            self.chat_message_manager.add_system_message_left_group(self.id, user)
            self.item['messageCount'] = self.item.get('messageCount', 0) + 1

        return self

    def delete_group_chat(self):
        assert self.type == enums.ChatType.GROUP, 'may not be called for non-GROUP chats'

        transacts = [self.dynamo.transact_delete(self.id, expected_user_count=0)]
        self.dynamo.client.transact_write_items(transacts)
        self.chat_message_manager.truncate_chat_messages(self.id)

    def delete_direct_chat(self):
        assert self.type == enums.ChatType.DIRECT, 'may not be called for non-DIRECT chats'
        user_id_1, user_id_2 = self.item['gsiA1PartitionKey'].split('/')[1:3]

        # first delete the chat and the memberships (so the chat never appears with no messages)
        transacts = [
            self.dynamo.transact_delete(self.id, expected_user_count=2),
            self.member_dynamo.transact_delete(self.id, user_id_1),
            self.member_dynamo.transact_delete(self.id, user_id_2),
            self.user_manager.dynamo.transact_decrement_chat_count(user_id_1),
            self.user_manager.dynamo.transact_decrement_chat_count(user_id_2),
        ]
        self.dynamo.client.transact_write_items(transacts)

        # second iterate through the messages and delete them
        self.chat_message_manager.truncate_chat_messages(self.id)
