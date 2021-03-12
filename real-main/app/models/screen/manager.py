import collections
import logging

import pendulum

from app.clients import AmplitudeClient
from app.mixins.base import ManagerBase
from app.mixins.view.manager import ViewManagerMixin

from .model import Screen

logger = logging.getLogger()


class ScreenManager(ViewManagerMixin, ManagerBase):

    item_type = 'screen'

    def __init__(self, clients, managers=None):
        super().__init__(clients, managers=managers)
        managers = managers or {}
        managers['screen'] = self
        self.amplitude_client = AmplitudeClient()

    def init_screen(self, screen_name):
        view_dynamo = getattr(self, 'view_dynamo', None)
        return Screen(screen_name, view_dynamo=view_dynamo)

    def record_views(self, screens, user_id, viewed_at=None):
        for screen_name, view_count in dict(collections.Counter(screens)).items():
            self.init_screen(screen_name).record_view_count(user_id, view_count, viewed_at=viewed_at)

    def on_view_log_amplitude_event(self, screen_name, new_item, old_item=None):
        user_id = new_item['gsiA2PartitionKey'].split('/')[1]
        event_type = 'VISIT_SCREEN'
        event_items = {
            'name': screen_name,
            'datetime': pendulum.now().to_iso8601_string(),
        }
        self.amplitude_client.attr_log_event(user_id, event_type, event_items)
