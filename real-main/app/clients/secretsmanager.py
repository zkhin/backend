import json
import os

import boto3

CLOUDFRONT_KEY_PAIR_NAME = os.environ.get('SECRETSMANAGER_CLOUDFRONT_KEY_PAIR_NAME')


class SecretsManagerClient:
    def __init__(self, cloudfront_key_pair_name=CLOUDFRONT_KEY_PAIR_NAME):
        self.boto_client = boto3.client('secretsmanager')
        self.exceptions = self.boto_client.exceptions
        self.cloudfront_key_pair_name = cloudfront_key_pair_name

    def get_cloudfront_key_pair(self):
        if not hasattr(self, '_cloudfront_key_pair'):
            resp = self.boto_client.get_secret_value(SecretId=self.cloudfront_key_pair_name)
            self._cloudfront_key_pair = json.loads(resp['SecretString'])
        return self._cloudfront_key_pair
