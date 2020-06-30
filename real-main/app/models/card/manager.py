import logging
import uuid

import pendulum

from app import models

from . import enums, exceptions
from .appsync import CardAppSync
from .dynamo import CardDynamo
from .model import Card
from .postprocessor import CardPostProcessor

logger = logging.getLogger()


class CardManager:

    enums = enums
    exceptions = exceptions

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['card'] = self
        self.post_manager = managers.get('post') or models.PostManager(clients, managers=managers)
        self.user_manager = managers.get('user') or models.UserManager(clients, managers=managers)

        if 'appsync' in clients:
            self.appsync = CardAppSync(clients['appsync'])
        if 'dynamo' in clients:
            self.dynamo = CardDynamo(clients['dynamo'])
        if 'pinpoint' in clients:
            self.pinpoint_client = clients['pinpoint']

    @property
    def postprocessor(self):
        if not hasattr(self, '_postprocessor'):
            self._postprocessor = CardPostProcessor(
                appsync=getattr(self, 'appsync', None), user_manager=self.user_manager,
            )
        return self._postprocessor

    def get_card(self, card_id, strongly_consistent=False):
        item = self.dynamo.get_card(card_id, strongly_consistent=strongly_consistent)
        return self.init_card(item) if item else None

    def init_card(self, item):
        kwargs = {
            'card_dynamo': getattr(self, 'dynamo', None),
            'pinpoint_client': getattr(self, 'pinpoint_client', None),
            'post_manager': self.post_manager,
            'user_manager': self.user_manager,
        }
        return Card(item, **kwargs)

    def add_card(self, user_id, title, action, card_id=None, sub_title=None, created_at=None, notify_user_at=None):
        created_at = created_at or pendulum.now('utc')
        card_id = card_id or str(uuid.uuid4())
        add_card_kwargs = {
            'sub_title': sub_title,
            'created_at': created_at,
            'notify_user_at': notify_user_at,
        }
        card_item = self.dynamo.add_card(card_id, user_id, title, action, **add_card_kwargs)
        return self.init_card(card_item)

    def add_card_by_spec_if_dne(self, spec, now=None):
        if self.get_card(spec.card_id):
            return
        now = now or pendulum.now('utc')
        notify_user_at = now + spec.notify_user_after if spec.notify_user_after else None
        try:
            return self.add_card(
                spec.user_id, spec.title, spec.action, spec.card_id, created_at=now, notify_user_at=notify_user_at,
            )
        except self.exceptions.CardAlreadyExists:
            pass

    def remove_card_by_spec_if_exists(self, spec, now=None):
        card = self.get_card(spec.card_id)
        if not card:
            return
        card.delete()

    def truncate_cards(self, user_id):
        # delete all cards for the user
        with self.dynamo.client.table.batch_writer() as batch:
            for card_pk in self.dynamo.generate_cards_by_user(user_id, pks_only=True):
                batch.delete_item(Key=card_pk)

    def notify_users(self, now=None):
        "Send out push notifications to all users for cards as needed"
        now = pendulum.now('utc')
        total_count, success_count = 0, 0
        for card_id in self.dynamo.generate_card_ids_by_notify_user_at(now):
            card = self.get_card(card_id)
            success = card.notify_user()
            total_count += 1
            if success:
                success_count += 1
                card.delete()
            else:
                # give up on the first failure for now
                card.clear_notify_user_at()
        return total_count, success_count
