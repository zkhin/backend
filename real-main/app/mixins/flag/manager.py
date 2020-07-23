import logging

from .dynamo import FlagDynamo

logger = logging.getLogger()


class FlagManagerMixin:
    # users that have flagging superpowers
    flag_admin_usernames = ('real', 'ian')

    def __init__(self, clients, managers=None):
        super().__init__(clients, managers=managers)
        if 'dynamo' in clients:
            self.flag_dynamo = FlagDynamo(self.item_type, clients['dynamo'])

    def unflag_all_by_user(self, user_id):
        for item_id in self.flag_dynamo.generate_item_ids_by_user(user_id):
            # this could be performance and edge-case optimized
            self.get_model(item_id).unflag(user_id)

    def on_flag_add(self, item_id, new_item):
        raise NotImplementedError('Subclasses must implement')

    def on_flag_delete(self, item_id, old_item):
        self.dynamo.decrement_flag_count(item_id, fail_soft=True)

    def on_item_delete_delete_flags(self, item_id, old_item):
        self.flag_dynamo.delete_all_for_item(item_id)
