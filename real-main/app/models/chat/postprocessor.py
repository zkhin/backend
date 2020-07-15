class ChatPostProcessor:
    def __init__(
        self, dynamo=None, member_dynamo=None, user_manager=None,
    ):
        self.dynamo = dynamo
        self.member_dynamo = member_dynamo
        self.user_manager = user_manager

    def run(self, pk, sk, old_item, new_item):
        # if this is a member record, check if we went to or from zero unviewed messages
        if sk.startswith('member/'):
            user_id = sk.split('/')[1]
            old_count = old_item.get('messagesUnviewedCount', 0)
            new_count = new_item.get('messagesUnviewedCount', 0)
            if old_count == 0 and new_count > 0:
                self.user_manager.dynamo.increment_chats_with_unviewed_messages_count(user_id)
            if old_count > 0 and new_count == 0:
                self.user_manager.dynamo.decrement_chats_with_unviewed_messages_count(user_id, fail_soft=True)
