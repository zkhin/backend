import logging
import uuid

import pendulum

from app import models

from .appsync import CardAppSync
from .dynamo import CardDynamo
from .enums import CardNotificationType
from .exceptions import CardAlreadyExists
from .model import Card
from .specs import ChatCardSpec, RequestedFollowersCardSpec

logger = logging.getLogger()


class CardManager:
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

    def get_card(self, card_id, strongly_consistent=False):
        item = self.dynamo.get_card(card_id, strongly_consistent=strongly_consistent)
        return self.init_card(item) if item else None

    def init_card(self, item):
        kwargs = {
            'appsync': getattr(self, 'appsync', None),
            'dynamo': getattr(self, 'dynamo', None),
            'pinpoint_client': getattr(self, 'pinpoint_client', None),
            'post_manager': self.post_manager,
            'user_manager': self.user_manager,
        }
        return Card(item, **kwargs)

    def add_card(
        self, user_id, title, action, card_id=None, sub_title=None, created_at=None, notify_user_at=None
    ):
        created_at = created_at or pendulum.now('utc')
        card_id = card_id or str(uuid.uuid4())
        add_card_kwargs = {
            'sub_title': sub_title,
            'created_at': created_at,
            'notify_user_at': notify_user_at,
        }
        card_item = self.dynamo.add_card(card_id, user_id, title, action, **add_card_kwargs)
        return self.init_card(card_item)

    def add_or_update_card_by_spec(self, spec, now=None):
        now = now or pendulum.now('utc')

        if getattr(spec, 'only_usernames', None):
            user = self.user_manager.get_user(spec.user_id)
            if user.username not in spec.only_usernames:
                return None

        notify_user_at = now + spec.notify_user_after if spec.notify_user_after else None
        try:
            return self.add_card(
                spec.user_id,
                spec.title,
                spec.action,
                spec.card_id,
                created_at=now,
                notify_user_at=notify_user_at,
            )
        except CardAlreadyExists:
            card_item = self.dynamo.update_title(spec.card_id, spec.title)
            return self.init_card(card_item)

    def remove_card_by_spec_if_exists(self, spec, now=None):
        card = self.get_card(spec.card_id)
        if not card:
            return
        card.delete()

    def truncate_cards(self, user_id):
        "Delete all cards for the user"
        generator = self.dynamo.generate_cards_by_user(user_id, pks_only=True)
        self.dynamo.client.batch_delete_items(generator)

    def notify_users(self, now=None, only_usernames=None):
        """
        Send out push notifications to all users for cards as needed.
        Use `only_usernames` if you don't want to send notifcations to all users.
        """
        # determine which users we should be sending notifcations to, if we're only doing some
        if only_usernames is None:
            only_user_ids = None
        elif only_usernames == []:
            return 0, 0
        else:
            only_users = [self.user_manager.get_user_by_username(username) for username in only_usernames]
            only_user_ids = [user.id for user in only_users if user]

        # send on notifcations for cards for those users
        now = pendulum.now('utc')
        total_count, success_count = 0, 0
        for card_id in self.dynamo.generate_card_ids_by_notify_user_at(now, only_user_ids=only_user_ids):
            card = self.get_card(card_id)
            success_count += card.notify_user()
            total_count += 1
            card.clear_notify_user_at()
        return total_count, success_count

    def on_card_add(self, card_id, new_item):
        self.init_card(new_item).trigger_notification(CardNotificationType.ADDED)

    def on_card_edit(self, card_id, new_item, old_item):
        self.init_card(new_item).trigger_notification(CardNotificationType.EDITED)

    def on_card_delete(self, card_id, old_item):
        self.init_card(old_item).trigger_notification(CardNotificationType.DELETED)

    def on_user_delete(self, user_id, old_item):
        self.remove_card_by_spec_if_exists(ChatCardSpec(user_id))
        self.remove_card_by_spec_if_exists(RequestedFollowersCardSpec(user_id))
