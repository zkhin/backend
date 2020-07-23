import logging

from .dynamo import ViewDynamo

logger = logging.getLogger()


class ViewManagerMixin:
    def __init__(self, clients, managers=None):
        super().__init__(clients, managers=managers)
        if 'dynamo' in clients:
            self.view_dynamo = ViewDynamo(self.item_type, clients['dynamo'])

    def record_views(self, item_ids, user_id, viewed_at=None):
        raise NotImplementedError  # subclasses must implement

    def on_item_delete_delete_views(self, item_id, old_item):
        pk_generator = self.view_dynamo.generate_views(item_id, pks_only=True)
        self.view_dynamo.delete_views(pk_generator)
