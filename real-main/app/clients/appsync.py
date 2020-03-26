"""
Inspiration from
    - https://gist.github.com/bencord0/70f9de572f0e284c94b7bcbf918dc0eb
    - https://github.com/phalt/gql_py
"""

import logging
import os

from boto3.session import Session as AWSSession
from gql_py import Gql
from requests import Session
from requests_aws4auth import AWS4Auth

APPSYNC_GRAPHQL_URL = os.environ.get('APPSYNC_GRAPHQL_URL')

logger = logging.getLogger()


class AppSyncClient:

    service_name = 'appsync'
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }

    def __init__(self, appsync_graphql_url=APPSYNC_GRAPHQL_URL):
        self.appsync_graphql_url = appsync_graphql_url

    def send(self, query, variables):
        aws_session = AWSSession()
        creds = aws_session.get_credentials().get_frozen_credentials()

        session = Session()
        session.auth = AWS4Auth(creds.access_key, creds.secret_key, aws_session.region_name, self.service_name,
                                session_token=creds.token)
        session.headers = self.headers

        api = Gql(api=self.appsync_graphql_url, session=session)
        resp = api.send(query=query, variables=variables)
        if not resp.ok:
            raise Exception(
                f'Error querying appsync: `{resp.errors}` with query `{query}` and variables `{variables}`'
            )
