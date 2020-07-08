import logging

logger = logging.getLogger()


class UserPostProcessor:
    def __init__(self, dynamo=None, manager=None):
        self.dynamo = dynamo
        self.manager = manager

    def run(self, pk, sk, old_item, new_item):
        assert sk == 'profile', 'Should only be called for user profile item'
        if new_item:
            self.manager.init_user(new_item).on_add_or_edit(old_item)
        else:
            self.manager.init_user(old_item).on_delete()

    def comment_added(self, user_id):
        self.dynamo.increment_comment_count(user_id)

    def comment_deleted(self, user_id):
        self.dynamo.decrement_comment_count(user_id, fail_soft=True)
        self.dynamo.increment_comment_deleted_count(user_id)
