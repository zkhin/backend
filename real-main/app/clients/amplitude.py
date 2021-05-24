import json
import logging
import time

import requests

from app.utils import DecimalJsonEncoder

logger = logging.getLogger()

API_URL = 'https://api2.amplitude.com/2/httpapi'
DISABLED = 'DISABLED'


class AmplitudeClient:
    def __init__(self, api_key_getter):
        self.api_key_getter = api_key_getter
        self.session = requests.Session()
        self.session.headers = {'Content-Type': 'application/json'}
        self.session.hooks = {'response': lambda r, *args, **kwargs: r.raise_for_status()}

    @property
    def api_key(self):
        if not hasattr(self, '_api_key'):
            self._api_key = self.api_key_getter()['apiKey']
        return self._api_key

    def log_event(self, user_id, event_type, event_properties):
        event = self.build_event(user_id, event_type, event_properties)
        self.send_events([event])

    def build_event(self, user_id, event_type, event_properties):
        return {
            'user_id': user_id,
            'event_type': event_type,
            'event_properties': event_properties,
            'time': int(time.time() * 1000),  # integer epoch time in milliseconds
        }

    def send_events(self, events):
        if self.api_key == DISABLED:
            return
        # https://developers.amplitude.com/docs/http-api-v2#uploadrequestbody
        data = json.dumps({'api_key': self.api_key, 'events': events}, cls=DecimalJsonEncoder)
        try:
            self.session.post(API_URL, data=data)
        except Exception as err:
            logger.warning(f'Failed to send events to Amplitude: {err}')
