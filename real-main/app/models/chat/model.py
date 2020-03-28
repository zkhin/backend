import logging

from . import enums, exceptions

logger = logging.getLogger()


class Chat:

    enums = enums
    exceptions = exceptions

    def __init__(self, item, chat_dynamo, chat_message_manager=None, user_manager=None):
        self.dynamo = chat_dynamo
        self.item = item
        if chat_message_manager:
            self.chat_message_manager = chat_message_manager
        if user_manager:
            self.user_manager = user_manager
        # immutables
        self.id = item['chatId']
        self.type = self.item['chatType']

    def refresh_item(self, strongly_consistent=False):
        self.item = self.dynamo.get_chat(self.id, strongly_consistent=strongly_consistent)
        return self

    def update_memberships_last_message_activity_at(self, now):
        # Note that dynamo has no support for batch updates.
        # This update will need to be made async at some scale (chats with 1000+ members?)
        for user_id in self.dynamo.generate_chat_membership_user_ids_by_chat(self.id):
            self.dynamo.update_chat_membership_last_message_activity_at(self.id, user_id, now)

    def leave_chat(self, user_id):
        if self.type == enums.ChatType.DIRECT:
            return self.delete_direct_chat(leaving_user_id=user_id)

        raise NotImplementedError('TODO: leave group chats')

    def delete_direct_chat(self, leaving_user_id=None):
        assert self.type == enums.ChatType.DIRECT, 'may not be called for non-DIRECT chats'
        user_ids = self.item['gsiA1PartitionKey'].split('/')[1:3]
        if leaving_user_id is not None and leaving_user_id not in user_ids:
            raise Exception(f'User `{leaving_user_id}` not authorized to delete chat `{self.id}`')

        # first delete the chat and the memberships (so the chat never appears with no messages)
        transacts = [
            self.dynamo.transact_delete_chat(self.id),
            self.dynamo.transact_delete_chat_membership(self.id, user_ids[0]),
            self.dynamo.transact_delete_chat_membership(self.id, user_ids[1]),
            self.user_manager.dynamo.transact_decrement_chat_count(user_ids[0]),
            self.user_manager.dynamo.transact_decrement_chat_count(user_ids[1]),
        ]
        self.dynamo.client.transact_write_items(transacts)

        # second iterate through the messages and delete them
        self.chat_message_manager.truncate_chat_messages(self.id)

    def delete_group_chat(self, leaving_user_id=None):
        assert self.type == enums.ChatType.GROUP, 'may only be called for GROUP chats'

        raise NotImplementedError('TODO: delete group chats')
