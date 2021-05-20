import json
import logging
from decimal import Decimal

import requests

logger = logging.getLogger()


API_URL = 'https://api.idanalyzer.com'
DISABLED = 'DISABLED'


class IdAnalyzerClient:
    def __init__(self, api_key_getter):
        self.api_key_getter = api_key_getter

    @property
    def api_key(self):
        if not hasattr(self, '_api_key'):
            self._api_key = self.api_key_getter()['apiKey']
        return self._api_key

    def verify_id(self, frontside_image):
        if self.api_key == DISABLED:
            return
        # https://developer.idanalyzer.com/coreapi_reference.html
        payload = {'apikey': self.api_key, 'file_base64': frontside_image, 'authenticate': True}
        r = requests.post(API_URL, json=payload)
        result = r.json()

        if 'error' in result:
            # failed
            raise Exception(
                f"ID verification service error `{str(result['error']['code'])}` with body `{result['error']['message']}`"
            )
        else:
            # success
            result = json.loads(json.dumps(result), parse_float=Decimal)
            return {
                'result': result.get('result', {}),
                'authentication': result.get('authentication', {}),
            }
