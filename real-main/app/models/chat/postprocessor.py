import pendulum

from app.models.card.specs import ChatCardSpec


class ChatPostProcessor:
    def __init__(
        self,
        dynamo=None,
        member_dynamo=None,
        view_dynamo=None,
        card_manager=None,
        chat_message_manager=None,
        user_manager=None,
    ):
        self.dynamo = dynamo
        self.member_dynamo = member_dynamo
        self.view_dynamo = view_dynamo
        self.card_manager = card_manager
        self.chat_message_manager = chat_message_manager
        self.user_manager = user_manager

    def run(self, pk, sk, old_item, new_item):
        chat_id = pk.split('/')[1]

        # if this is a member record, check if we went to or from zero unviewed messages
        if sk.startswith('member/'):
            user_id = sk.split('/')[1]
            old_count = (old_item or {}).get('messagesUnviewedCount', 0)
            new_count = (new_item or {}).get('messagesUnviewedCount', 0)
            if old_count == 0 and new_count != 0:
                self.user_manager.dynamo.increment_chats_with_unviewed_messages_count(user_id)
            if old_count != 0 and new_count == 0:
                self.user_manager.dynamo.decrement_chats_with_unviewed_messages_count(user_id, fail_soft=True)

        # if this is a view record, clear unviewed messages and the chat card
        if sk.startswith('view/'):
            user_id = sk.split('/')[1]
            # only adds or edits of view items
            if new_item:
                self.member_dynamo.clear_messages_unviewed_count(chat_id, user_id)
                self.card_manager.remove_card_by_spec_if_exists(ChatCardSpec(user_id))

    def chat_message_added(self, chat_id, author_user_id, created_at):
        # Note that dynamo has no support for batch updates.
        self.dynamo.update_last_message_activity_at(chat_id, created_at, fail_soft=True)
        self.dynamo.increment_messages_count(chat_id)

        # for each memeber of the chat
        #   - update the last message activity timestamp (controls chat ordering)
        #   - for everyone except the author, increment their 'messagesUnviewedCount'
        #     and add a 'You have new chat messages' card if it doesn't already exist
        for user_id in self.member_dynamo.generate_user_ids_by_chat(chat_id):
            self.member_dynamo.update_last_message_activity_at(chat_id, user_id, created_at, fail_soft=True)
            if user_id != author_user_id:
                self.member_dynamo.increment_messages_unviewed_count(chat_id, user_id)
                self.card_manager.add_card_by_spec_if_dne(ChatCardSpec(user_id), now=created_at)

    def chat_message_deleted(self, chat_id, message_id, author_user_id, created_at):
        # Note that dynamo has no support for batch updates.
        self.dynamo.decrement_messages_count(chat_id, fail_soft=True)

        # for each memeber of the chat other than the author
        #   - delete any view record that exists directly on the message
        #   - determine if the message had status 'unviewed', and if so, then decrement the unviewed message counter
        for user_id in self.member_dynamo.generate_user_ids_by_chat(chat_id):
            if user_id != author_user_id:
                message_view_deleted = self.chat_message_manager.view_dynamo.delete_view(message_id, user_id)
                chat_view_item = self.view_dynamo.get_view(chat_id, user_id)
                chat_last_viewed_at = pendulum.parse(chat_view_item['lastViewedAt']) if chat_view_item else None
                is_viewed = message_view_deleted or (chat_last_viewed_at and chat_last_viewed_at > created_at)
                if not is_viewed:
                    self.member_dynamo.decrement_messages_unviewed_count(chat_id, user_id, fail_soft=True)

    def chat_message_view_added(self, chat_id, user_id):
        self.member_dynamo.decrement_messages_unviewed_count(chat_id, user_id, fail_soft=True)
