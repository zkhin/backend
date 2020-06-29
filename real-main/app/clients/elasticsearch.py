import json
import logging
import os

import boto3
import requests
import requests_aws4auth

logger = logging.getLogger()

ELASTICSEARCH_DOMAIN = os.environ.get('ELASTICSEARCH_DOMAIN')


class ElasticSearchClient:

    service = 'es'
    headers = {'Content-Type': 'application/json'}
    keys = [
        'userId',
        'username',
        'fullName',
    ]

    def __init__(self, domain=ELASTICSEARCH_DOMAIN):
        assert domain, '`domain` is required'
        self.domain = domain

    @property
    def awsauth(self):
        if not hasattr(self, '_awsauth'):
            session = boto3.Session()
            credentials = session.get_credentials().get_frozen_credentials()
            self._awsauth = requests_aws4auth.AWS4Auth(
                credentials.access_key,
                credentials.secret_key,
                session.region_name,
                self.service,
                session_token=credentials.token,
            )
        return self._awsauth

    def query_users(self, query):
        "`query` should be dict-like structure that can be serialized to json"
        url = f'https://{self.domain}/users/_search'
        resp = requests.get(url, auth=self.awsauth, json={'query': query}, headers=self.headers)
        if resp.status_code != 200:
            logging.warning(f'ElasticSearch: Recieved non-200 response of {resp.status_code} when querying users')
        return resp.json()

    def build_user_url(self, user_id):
        return f'https://{self.domain}/users/_doc/{user_id}'

    def build_user_doc(self, user_item):
        return {k: user_item[k] for k in self.keys if k in user_item}

    def add_user(self, user_id, user_item):
        doc = self.build_user_doc(user_item)
        url = self.build_user_url(user_id)
        logging.info(f'ElasticSearch: Adding user to index at `{url}` ' + json.dumps(doc))
        resp = requests.put(url, auth=self.awsauth, json=doc, headers=self.headers)
        if resp.status_code != 201:
            logging.warning(f'ElasticSearch: Recieved non-201 response of {resp.status_code} when adding user')

    def update_user(self, user_id, old_user_item, new_user_item):
        old_doc = self.build_user_doc(old_user_item)
        new_doc = self.build_user_doc(new_user_item)
        if old_doc == new_doc:
            # no changes that effect elasticsearch
            return
        url = self.build_user_url(user_id)
        logging.info(f'ElasticSearch: Updating user in index at `{url}` ' + json.dumps(new_doc))
        resp = requests.put(url, auth=self.awsauth, json=new_doc, headers=self.headers)
        if resp.status_code != 200:
            logging.warning(f'ElasticSearch: Recieved non-200 response of {resp.status_code} when updating user')

    def delete_user(self, user_id):
        url = self.build_user_url(user_id)
        logging.info(f'ElasticSearch: Deleting user from index at `{url}`')
        resp = requests.delete(url, auth=self.awsauth)
        if resp.status_code != 200:
            logging.warning(f'ElasticSearch: Recieved non-200 response of {resp.status_code} when deleting user')
