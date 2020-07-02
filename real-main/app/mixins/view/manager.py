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
