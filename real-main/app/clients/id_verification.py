import base64
import logging

import requests

logger = logging.getLogger()


API_URL = 'https://netverify.com/api/netverify/v2/performNetverify'
IDANALYZER_API_URL = 'https://api.idanalyzer.com'


class IdVerificationClient:
    def __init__(self, api_creds_getter):
        self.api_creds_getter = api_creds_getter

    @property
    def api_creds(self):
        if not hasattr(self, '_api_creds'):
            self._api_creds = self.api_creds_getter()
        return self._api_creds

    @property
    def auth_token(self):
        api_token = self.api_creds['apiToken']
        secret = self.api_creds['secret']
        return base64.b64encode(f'{api_token}:{secret}'.encode('utf-8')).decode('utf-8')

    @property
    def callback_url(self):
        return self.api_creds['callbackUrl']

    @property
    def id_analyzer_api_key(self):
        return self.api_creds.get('idAnalyzerApiKey')

    def verify_id(self, user_id, frontside_image, country, id_type, mime_type):
        # https://github.com/Jumio/implementation-guides/blob/master/netverify/performNetverify.md
        headers = {
            'User-Agent': 'REAL Social real-backend/v1.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Basic {self.auth_token}',
        }

        data = {
            'merchantIdScanReference': user_id,
            'frontsideImage': frontside_image,
            'country': country,
            'idType': id_type,
            'frontsideImageMimeType': mime_type,
            'callbackUrl': f'{self.callback_url}/id-verification/{user_id}/callback',
        }

        resp = requests.post(API_URL, headers=headers, json=data)
        if resp.status_code != 200:
            raise Exception(f'ID verification service error `{resp.status_code}` with body `{resp.text}`')
        try:
            return resp.json()['jumioIdScanReference']
        except Exception as err:
            raise Exception(
                f'Unable to parse response from jumio verification service with body: `{resp.text}`'
            ) from err

    def verify_id_with_id_analyzer(self, frontside_image):
        if not self.id_analyzer_api_key:
            return
        # https://developer.idanalyzer.com/coreapi_reference.html
        payload = {'apikey': self.id_analyzer_api_key, 'file_base64': frontside_image}
        r = requests.post(IDANALYZER_API_URL, data=payload)
        result = r.json()

        if 'error' in result:
            # failed
            raise Exception(
                f"ID verification service error `{str(result['error']['code'])}` with body `{result['error']['message']}`"
            )
        else:
            # success
            return result
