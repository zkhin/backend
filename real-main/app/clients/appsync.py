import logging
import os

from boto3.session import Session as AWSSession
from gql.transport.requests import RequestsHTTPTransport
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
        auth = AWS4Auth(creds.access_key, creds.secret_key, aws_session.region_name, self.service_name,
                        session_token=creds.token)
        transport = RequestsHTTPTransport(url=self.appsync_graphql_url, use_json=True, headers=self.headers,
                                          auth=auth)
        resp = transport.execute(query, variables)
        if resp.errors:
            raise Exception(f'Error querying appsync: `{resp.errors}` with query `{query}`, variables `{variables}`')
