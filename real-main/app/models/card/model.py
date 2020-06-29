import logging

import pendulum

from . import enums, exceptions, specs

logger = logging.getLogger()


class Card:

    enums = enums
    exceptions = exceptions

    def __init__(
        self, item, card_appsync=None, card_dynamo=None, pinpoint_client=None, post_manager=None, user_manager=None
    ):
        self.appsync = card_appsync
        self.dynamo = card_dynamo
        self.pinpoint_client = pinpoint_client
        self.post_manager = post_manager
        self.user_manager = user_manager

        self.item = item
        # immutables
        self.id = item['partitionKey'][len('card/') :]
        self.user_id = item['gsiA1PartitionKey'][len('user/') :]
        self.created_at = pendulum.parse(item['gsiA1SortKey'][len('card/') :])
        self.spec = specs.CardSpec.from_card_id(self.id)

    @property
    def user(self):
        if not hasattr(self, '_user'):
            self._user = self.user_manager.get_user(self.user_id) if self.user_id else None
        return self._user

    @property
    def post(self):
        if not hasattr(self, '_post'):
            post_id = self.spec.post_id if self.spec else None
            self._post = self.post_manager.get_post(post_id) if post_id else None
        return self._post

    @property
    def has_thumbnail(self):
        return bool(self.spec and self.spec.post_id)

    @property
    def notify_user_at(self):
        return pendulum.parse(self.item['gsiK1SortKey']) if 'gsiK1SortKey' in self.item else None

    def refresh_item(self, strongly_consistent=False):
        self.item = self.dynamo.get_card(self.id, strongly_consistent=strongly_consistent)
        return self

    def serialize(self, caller_user_id):
        resp = self.item.copy()
        resp['cardId'] = self.id
        return resp

    def get_image_url(self, size):
        return self.post.get_image_readonly_url(size) if self.post else None

    def notify_user(self):
        "Returns bool indicating if notification was successfully sent to user"
        # just APNS for now
        return self.pinpoint_client.send_user_apns(
            self.user_id, self.item['action'], self.item['title'], body=self.item.get('subTitle')
        )

    def clear_notify_user_at(self):
        self.item = self.dynamo.clear_notify_user_at(self.id)
        return self

    def delete(self):
        self.dynamo.delete_card(self.id)
        self.appsync.trigger_notification(
            enums.CardNotificationType.DELETED,
            self.user_id,
            self.id,
            self.item['title'],
            self.item['action'],
            sub_title=self.item.get('subTitle'),
        )
        return self
