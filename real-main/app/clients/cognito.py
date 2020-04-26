import logging
import os
import random
import string

import boto3

AWS_REGION = os.environ.get('AWS_REGION')
COGNITO_USER_POOL_ID = os.environ.get('COGNITO_USER_POOL_ID')
COGNITO_BACKEND_CLIENT_ID = os.environ.get('COGNITO_USER_POOL_BACKEND_CLIENT_ID')

logger = logging.getLogger()


class CognitoClient:

    def __init__(self, user_pool_id=COGNITO_USER_POOL_ID, client_id=COGNITO_BACKEND_CLIENT_ID,
                 aws_region=AWS_REGION):
        assert user_pool_id, "Cognito user pool id is required"
        assert client_id, "Cognito user pool client id is required"

        self.user_pool_id = user_pool_id
        self.client_id = client_id
        self.boto_client = boto3.client('cognito-idp')

        self.userPoolLoginsKey = f'cognito-idp.{aws_region}.amazonaws.com/{user_pool_id}'
        self.googleLoginsKey = 'accounts.google.com'
        self.facebookLoginsKey = 'graph.facebook.com'

    def create_user_pool_entry(self, user_id, email, username):
        cognito_special_chars = '^$*.[]{}()?-"!@#%&/\\,><\':;|_~`'
        characters = string.ascii_uppercase + string.ascii_lowercase + string.digits + cognito_special_chars
        password = ''.join(random.choices(characters, k=95)) + 'Aa1!'

        # set them up in the user pool
        self.boto_client.admin_create_user(
            UserPoolId=self.user_pool_id,
            Username=user_id,
            MessageAction='SUPPRESS',
            UserAttributes=[{
                'Name': 'email',
                'Value': email,
            }, {
                'Name': 'email_verified',
                'Value': 'true',
            }, {
                'Name': 'preferred_username',
                'Value': username.lower(),
            }],
        )
        self.boto_client.admin_set_user_password(
            UserPoolId=self.user_pool_id,
            Username=user_id,
            Password=password,
            Permanent=True,
        )

        # login as them
        resp = self.boto_client.admin_initiate_auth(
            UserPoolId=self.user_pool_id,
            ClientId=self.client_id,
            AuthFlow='ADMIN_USER_PASSWORD_AUTH',
            AuthParameters={
                'USERNAME': user_id,
                'PASSWORD': password,
            },
        )
        return resp['AuthenticationResult']['IdToken']

    def link_identity_pool_entries(self, user_id, cognito_id_token=None, facebook_access_token=None,
                                   google_id_token=None):
        identity_pool_client = boto3.client('cognito-identity')
        logins = {}
        if cognito_id_token:
            logins[self.userPoolLoginsKey] = cognito_id_token
        if facebook_access_token:
            logins[self.facebookLoginsKey] = facebook_access_token
        if google_id_token:
            logins[self.googleLoginsKey] = google_id_token
        identity_pool_client.get_credentials_for_identity(IdentityId=user_id, Logins=logins)

    def set_user_attributes(self, user_id, attrs):
        """
        Set a user's attributes
        The 'attrs' parameter should be dictionary of {name: value}
        """
        self.boto_client.admin_update_user_attributes(
            UserPoolId=self.user_pool_id,
            Username=user_id,
            UserAttributes=[{
                'Name': name,
                'Value': value,
            } for name, value in attrs.items()],
        )

    def clear_user_attribute(self, user_id, name):
        self.boto_client.admin_delete_user_attributes(
            UserPoolId=self.user_pool_id,
            Username=user_id,
            UserAttributeNames=[name],
        )

    def get_user_attributes(self, user_id):
        boto_resp = self.boto_client.admin_get_user(
            UserPoolId=self.user_pool_id,
            Username=user_id,
        )
        return {ua['Name']: ua['Value'] for ua in boto_resp['UserAttributes']}

    def verify_user_attribute(self, access_token, attribute_name, code):
        "Raises an exception for failure, else success"
        self.boto_client.verify_user_attribute(
            AccessToken=access_token,
            AttributeName=attribute_name,
            Code=code,
        )

    def get_user_status(self, user_id):
        boto_resp = self.boto_client.admin_get_user(
            UserPoolId=self.user_pool_id,
            Username=user_id,
        )
        return boto_resp['UserStatus']

    def list_unconfirmed_user_pool_entries(self):
        boto_resp = self.boto_client.list_users(
            UserPoolId=self.user_pool_id,
            Filter='cognito:user_status = "UNCONFIRMED"'
        )
        user_items = []
        for resp_item in boto_resp['Users']:
            user_item = {ua['Name']: ua['Value'] for ua in resp_item['Attributes']}
            user_item['Username'] = resp_item['Username']
            user_item['UserCreateDate'] = resp_item['UserCreateDate']
            user_item['UserLastModifiedDate'] = resp_item['UserLastModifiedDate']
            user_items.append(user_item)
        return user_items

    def delete_user_pool_entry(self, user_id):
        self.boto_client.admin_delete_user(
            UserPoolId=self.user_pool_id,
            Username=user_id,
        )
