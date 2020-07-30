import logging
import os
from uuid import uuid4

import boto3

COGNITO_USER_POOL_ID = os.environ.get('COGNITO_USER_POOL_ID')
COGNITO_BACKEND_CLIENT_ID = os.environ.get('COGNITO_USER_POOL_BACKEND_CLIENT_ID')

logger = logging.getLogger()


class CognitoClient:
    def __init__(self, user_pool_id=COGNITO_USER_POOL_ID, client_id=COGNITO_BACKEND_CLIENT_ID):
        assert user_pool_id, "Cognito user pool id is required"
        assert client_id, "Cognito user pool client id is required"

        self.user_pool_id = user_pool_id
        self.client_id = client_id
        self.user_pool_client = boto3.client('cognito-idp')
        self.identity_pool_client = boto3.client('cognito-identity')

        aws_region = boto3.Session().region_name
        self.userPoolLoginsKey = f'cognito-idp.{aws_region}.amazonaws.com/{user_pool_id}'
        self.googleLoginsKey = 'accounts.google.com'
        self.facebookLoginsKey = 'graph.facebook.com'
        self.appleLoginsKey = 'appleid.apple.com'

    def create_verified_user_pool_entry(self, user_id, username, email):
        self.user_pool_client.admin_create_user(
            UserPoolId=self.user_pool_id,
            Username=user_id,
            MessageAction='SUPPRESS',
            UserAttributes=[
                {'Name': 'email', 'Value': email},
                {'Name': 'email_verified', 'Value': 'true'},
                {'Name': 'preferred_username', 'Value': username.lower()},
            ],
        )
        # If we don't set their password to something, cognito will put the account in
        # a FORCE_CHANGE_PASSWORD which does not allow them to reset their password, which
        # we use to allow users to add a password-based login to their account (assuming
        # they started with a federate auth login).
        self.user_pool_client.admin_set_user_password(
            UserPoolId=self.user_pool_id, Username=user_id, Password=str(uuid4()), Permanent=True,
        )

    def get_user_pool_id_token(self, user_id):
        resp = self.user_pool_client.admin_initiate_auth(
            UserPoolId=self.user_pool_id,
            ClientId=self.client_id,
            AuthFlow='CUSTOM_AUTH',
            AuthParameters={'USERNAME': user_id},
        )
        return resp['AuthenticationResult']['IdToken']

    def link_identity_pool_entries(
        self, user_id, apple_token=None, cognito_token=None, facebook_token=None, google_token=None
    ):
        """
        The `apple_token`, if provided, should be the apple id token.
        The `cognito_token`, if provided, should be the cognito id token.
        The `facebook_token`, if provided, should be the facebook access token.
        The `google_token`, if provided, should be the google id token.
        """
        logins = {}
        if apple_token:
            logins[self.appleLoginsKey] = apple_token
        if cognito_token:
            logins[self.userPoolLoginsKey] = cognito_token
        if facebook_token:
            logins[self.facebookLoginsKey] = facebook_token
        if google_token:
            logins[self.googleLoginsKey] = google_token
        self.identity_pool_client.get_credentials_for_identity(IdentityId=user_id, Logins=logins)

    def set_user_attributes(self, user_id, attrs):
        """
        Set a user's attributes
        The 'attrs' parameter should be dictionary of {name: value}
        """
        self.user_pool_client.admin_update_user_attributes(
            UserPoolId=self.user_pool_id,
            Username=user_id,
            UserAttributes=[{'Name': name, 'Value': value} for name, value in attrs.items()],
        )

    def clear_user_attribute(self, user_id, name):
        self.user_pool_client.admin_delete_user_attributes(
            UserPoolId=self.user_pool_id, Username=user_id, UserAttributeNames=[name],
        )

    def get_user_attributes(self, user_id):
        boto_resp = self.user_pool_client.admin_get_user(UserPoolId=self.user_pool_id, Username=user_id)
        return {ua['Name']: ua['Value'] for ua in boto_resp['UserAttributes']}

    def verify_user_attribute(self, access_token, attribute_name, code):
        "Raises an exception for failure, else success"
        self.user_pool_client.verify_user_attribute(
            AccessToken=access_token, AttributeName=attribute_name, Code=code,
        )

    def get_user_status(self, user_id):
        boto_resp = self.user_pool_client.admin_get_user(UserPoolId=self.user_pool_id, Username=user_id)
        return boto_resp['UserStatus']

    def list_unconfirmed_user_pool_entries(self):
        boto_resp = self.user_pool_client.list_users(
            UserPoolId=self.user_pool_id, Filter='cognito:user_status = "UNCONFIRMED"'
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
        self.user_pool_client.admin_delete_user(
            UserPoolId=self.user_pool_id, Username=user_id,
        )

    def delete_identity_pool_entry(self, user_id):
        self.identity_pool_client.delete_identities(IdentityIdsToDelete=[user_id])
