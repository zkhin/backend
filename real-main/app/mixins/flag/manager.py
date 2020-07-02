import logging

from .dynamo import FlagDynamo

logger = logging.getLogger()


class FlagManagerMixin:
    def __init__(self, clients, managers=None):
        super().__init__(clients, managers=managers)
        if 'dynamo' in clients:
            self.flag_dynamo = FlagDynamo(self.item_type, clients['dynamo'])

    def unflag_all_by_user(self, user_id):
        for item_id in self.flag_dynamo.generate_item_ids_by_user(user_id):
            # this could be performance and edge-case optimized
            self.get_model(item_id).unflag(user_id)
