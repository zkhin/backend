import base64
import json
import logging

import requests

logger = logging.getLogger()


API_URL = 'https://netverify.com/api/netverify/v2/performNetverify'


class IdVerificationClient:
    def __init__(self, api_creds_getter):
        self.api_creds_getter = api_creds_getter

    @property
    def api_creds(self):
        if not hasattr(self, '_api_creds'):
            self._api_creds = self.api_creds_getter()
        return self._api_creds

    @property
    def api_token(self):
        if not self.api_creds:
            return
        api_token = self.api_creds['apiToken']
        secret = self.api_creds['secret']
        return base64.b64encode(f'{api_token}:{secret}'.encode('utf-8')).decode('utf-8')

    @property
    def callback_url(self):
        if not self.api_creds:
            return
        return self.api_creds['callbackUrl']

    def verify_id(self, user_id, frontside_image, country, id_type, mime_type):
        if not self.api_token:
            return
        # https://github.com/Jumio/implementation-guides/blob/master/netverify/performNetverify.md
        headers = {
            'User-Agent': 'REAL Social real-backend/v1.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Basic {self.api_token}',
        }

        data = json.dumps(
            {
                'merchantIdScanReference': user_id,
                'frontsideImage': frontside_image,
                'country': country,
                'idType': id_type,
                'frontsideImageMimeType': mime_type,
                'callbackUrl': f'{self.callback_url}/id-verification/{user_id}/callback',
            }
        )

        resp = requests.post(API_URL, headers=headers, json=data)
        if resp.status_code != 200:
            raise Exception(f'ID verification service error `{resp.status_code}` with body `{resp.text}`')
        try:
            return resp.json()['jumioIdScanReference']
        except Exception as err:
            raise Exception(
                f'Unable to parse response from jumio verification service with body: `{resp.text}`'
            ) from err
