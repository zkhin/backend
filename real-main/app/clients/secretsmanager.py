import json
import os

import boto3

CLOUDFRONT_KEY_PAIR_NAME = os.environ.get('SECRETSMANAGER_CLOUDFRONT_KEY_PAIR_NAME')
POST_VERIFICATION_API_CREDS_NAME = os.environ.get('SECRETSMANAGER_POST_VERIFICATION_API_CREDS_NAME')


class SecretsManagerClient:

    def __init__(self, cloudfront_key_pair_name=CLOUDFRONT_KEY_PAIR_NAME,
                 post_verification_api_creds_name=POST_VERIFICATION_API_CREDS_NAME):
        self.boto_client = boto3.client('secretsmanager')
        self.cloudfront_key_pair_name = cloudfront_key_pair_name
        self.post_verification_api_creds_name = post_verification_api_creds_name

    def get_cloudfront_key_pair(self):
        if not hasattr(self, '_cloudfront_key_pair'):
            resp = self.boto_client.get_secret_value(SecretId=self.cloudfront_key_pair_name)
            self._cloudfront_key_pair = json.loads(resp['SecretString'])
        return self._cloudfront_key_pair

    def get_post_verification_api_creds(self):
        if not hasattr(self, '_post_verification_api_creds'):
            resp = self.boto_client.get_secret_value(SecretId=self.post_verification_api_creds_name)
            self._post_verification_api_creds = json.loads(resp['SecretString'])
        return self._post_verification_api_creds
