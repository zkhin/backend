import json
import logging
import os
from decimal import Decimal

import requests
from aws_requests_auth.boto_utils import BotoAWSRequestsAuth

from app.utils import DecimalAsStringJsonEncoder

logger = logging.getLogger()

API_HOST = os.environ.get('REAL_TRANSACTIONS_API_HOST')
API_STAGE = os.environ.get('REAL_TRANSACTIONS_API_STAGE')
API_REGION = os.environ.get('REAL_TRANSACTIONS_API_REGION')

TRANSACTIONS_SERVICE_READY = False


class RealTransactionsClient:
    def __init__(
        self,
        api_host=API_HOST,
        api_stage=API_STAGE,
        api_region=API_REGION,
        transactions_service_ready=TRANSACTIONS_SERVICE_READY,
    ):
        self.api_root = f'https://{api_host}/{api_stage}'
        self.auth = BotoAWSRequestsAuth(aws_host=api_host, aws_region=api_region, aws_service='execute-api')
        self.session = requests.Session()
        self.session.hooks = {'response': lambda r, *args, **kwargs: r.raise_for_status()}
        self.transactions_service_ready = transactions_service_ready

    def pay_for_ad_view(self, viewer_id, ad_post_owner_id, ad_post_id, amount):
        assert isinstance(amount, Decimal), "'amount' must be a Decimal"
        if not self.transactions_service_ready:
            return
        url = f'{self.api_root}/pay_user_for_advertisement'
        data = {
            'advertiser_uuid': ad_post_owner_id,
            'amount': amount,
            'description': f'For view of ad with post id: {ad_post_id}',
            'viewer_uuid': viewer_id,
        }
        self.session.post(url, auth=self.auth, data=json.dumps(data, cls=DecimalAsStringJsonEncoder))

    def pay_for_post_view(self, viewer_id, post_owner_id, post_id, amount):
        assert isinstance(amount, Decimal), "'amount' must be a Decimal"
        if not self.transactions_service_ready:
            return
        url = f'{self.api_root}/pay_for_post_view'
        data = {
            'amount': amount,
            'post_owner_uuid': post_owner_id,
            'post_uuid': post_id,
            'viewer_uuid': viewer_id,
        }
        self.session.post(url, auth=self.auth, data=json.dumps(data, cls=DecimalAsStringJsonEncoder))
