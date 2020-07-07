class ChatPostProcessor:
    def __init__(
        self, dynamo=None, member_dynamo=None, user_manager=None,
    ):
        self.dynamo = dynamo
        self.member_dynamo = member_dynamo
        self.user_manager = user_manager

    def run(self, pk, sk, old_item, new_item):
        chat_id = pk.split('/')[1]

        # if this is a member record, check if we went to or from zero unviewed messages
        if sk.startswith('member/'):
            user_id = sk.split('/')[1]
            old_count = old_item.get('messagesUnviewedCount', 0)
            new_count = new_item.get('messagesUnviewedCount', 0)
            if old_count == 0 and new_count > 0:
                self.user_manager.dynamo.increment_chats_with_unviewed_messages_count(user_id)
            if old_count > 0 and new_count == 0:
                self.user_manager.dynamo.decrement_chats_with_unviewed_messages_count(user_id, fail_soft=True)

        # if this is a view record, clear unviewed messages
        if sk.startswith('view/'):
            user_id = sk.split('/')[1]
            # only adds or edits of view items
            if new_item:
                self.member_dynamo.clear_messages_unviewed_count(chat_id, user_id)

    def chat_message_view_added(self, chat_id, user_id):
        self.member_dynamo.decrement_messages_unviewed_count(chat_id, user_id, fail_soft=True)
