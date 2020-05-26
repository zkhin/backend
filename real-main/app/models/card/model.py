import logging

import pendulum

from . import enums, exceptions

logger = logging.getLogger()


class Card:

    enums = enums
    exceptions = exceptions

    def __init__(self, item, card_dynamo=None, user_manager=None):
        self.dynamo = card_dynamo
        self.user_manager = user_manager

        self.item = item
        # immutables
        self.id = item['partitionKey'][len('card/'):]
        self.user_id = item['gsiA1PartitionKey'][len('user/'):]
        self.created_at = pendulum.parse(item['gsiA1SortKey'][len('card/'):])

    @property
    def user(self):
        if not hasattr(self, '_user'):
            self._user = self.user_manager.get_user(self.user_id) if self.user_id else None
        return self._user

    def refresh_item(self, strongly_consistent=False):
        self.item = self.dynamo.get_card(self.id, strongly_consistent=strongly_consistent)
        return self

    def serialize(self, caller_user_id):
        resp = self.item.copy()
        resp['cardId'] = self.id
        return resp

    def delete(self):
        transacts = [
            self.dynamo.transact_delete_card(self.id),
            self.user_manager.dynamo.transact_card_deleted(self.user_id),
        ]
        transact_exceptions = [
            self.exceptions.CardDoesNotExist(self.id),
            self.exceptions.CardException('Unable to register card deleted on user item'),
        ]
        self.dynamo.client.transact_write_items(transacts, transact_exceptions)
        return self
