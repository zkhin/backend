import logging
import os

import boto3

COGNITO_USER_POOL_ID = os.environ.get('COGNITO_USER_POOL_ID')

logger = logging.getLogger()


class CognitoClient:

    def __init__(self, user_pool_id=COGNITO_USER_POOL_ID):
        assert user_pool_id, "Cognito user pool id is required"
        self.user_pool_id = user_pool_id
        self.boto_client = boto3.client('cognito-idp')

    def is_username_available(self, username):
        boto_resp = self.boto_client.list_users(
            UserPoolId=self.user_pool_id,
            AttributesToGet=[],
            Filter=f'preferred_username = "{username.lower()}"',
            Limit=1,
        )
        return not bool(boto_resp['Users'])
