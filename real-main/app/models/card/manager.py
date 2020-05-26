import logging

import pendulum
import uuid

from app import models

from . import enums, exceptions
from .model import Card
from .dynamo import CardDynamo

logger = logging.getLogger()


class CardManager:

    enums = enums
    exceptions = exceptions

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['card'] = self
        self.user_manager = managers.get('user') or models.UserManager(clients, managers=managers)

        if 'dynamo' in clients:
            self.dynamo = CardDynamo(clients['dynamo'])

    def get_card(self, card_id, strongly_consistent=False):
        item = self.dynamo.get_card(card_id, strongly_consistent=strongly_consistent)
        return self.init_card(item) if item else None

    def init_card(self, item):
        kwargs = {
            'card_dynamo': self.dynamo,
            'user_manager': self.user_manager,
        }
        return Card(item, **kwargs)

    def add_card(self, user_id, title, action, card_id=None, sub_title=None, now=None):
        now = now or pendulum.now('utc')
        card_id = card_id or str(uuid.uuid4())
        transacts = [
            self.dynamo.transact_add_card(card_id, user_id, title, action, sub_title=sub_title, now=now),
            self.user_manager.dynamo.transact_card_added(user_id),
        ]
        transact_exceptions = [
            self.exceptions.CardAlreadyExists(card_id),
            self.exceptions.CardException('Unable to register card added on user item'),
        ]
        self.dynamo.client.transact_write_items(transacts, transact_exceptions)
        return self.get_card(card_id, strongly_consistent=True)

    def add_well_known_card_if_dne(self, user_id, well_known_card, now=None):
        card_id = well_known_card.get_card_id(user_id)
        if self.get_card(card_id):
            return
        try:
            self.add_card(user_id, well_known_card.title, well_known_card.action, card_id, now=now)
        except self.exceptions.CardAlreadyExists:
            pass

    def remove_well_known_card_if_exists(self, user_id, well_known_card, now=None):
        card = self.get_card(well_known_card.get_card_id(user_id))
        if not card:
            return
        try:
            card.delete()
        except self.exceptions.CardDoesNotExist:
            pass

    def truncate_cards(self, user_id):
        # delete all cards for the user without bothering to adjust User.cardCount
        with self.dynamo.client.table.batch_writer() as batch:
            for card_pk in self.dynamo.generate_cards_by_user(user_id, pks_only=True):
                batch.delete_item(Key=card_pk)
