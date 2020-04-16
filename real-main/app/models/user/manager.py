import logging
import os
import random
import re

from app.models import block, follow, post, trending

from . import enums, exceptions
from .dynamo import UserDynamo
from .model import User
from .validate import UserValidate

logger = logging.getLogger()

S3_PLACEHOLDER_PHOTOS_DIRECTORY = os.environ.get('S3_PLACEHOLDER_PHOTOS_DIRECTORY')


class UserManager:

    enums = enums
    exceptions = exceptions
    client_names = ['cloudfront', 'cognito', 'dynamo', 'facebook', 'google', 's3_uploads', 's3_placeholder_photos']
    username_tag_regex = re.compile('@' + UserValidate.username_regex.pattern)

    def __init__(self, clients, managers=None, placeholder_photos_directory=S3_PLACEHOLDER_PHOTOS_DIRECTORY):
        managers = managers or {}
        managers['user'] = self
        self.block_manager = managers.get('block') or block.BlockManager(clients, managers=managers)
        self.follow_manager = managers.get('follow') or follow.FollowManager(clients, managers=managers)
        self.post_manager = managers.get('post') or post.PostManager(clients, managers=managers)
        self.trending_manager = managers.get('trending') or trending.TrendingManager(clients, managers=managers)

        self.clients = clients
        for client_name in self.client_names:
            if client_name in clients:
                setattr(self, f'{client_name}_client', clients[client_name])
        if 'dynamo' in clients:
            self.dynamo = UserDynamo(clients['dynamo'])
        self.validate = UserValidate()
        self.placeholder_photos_directory = placeholder_photos_directory

    def get_user(self, user_id, strongly_consistent=False):
        user_item = self.dynamo.get_user(user_id, strongly_consistent=strongly_consistent)
        return self.init_user(user_item) if user_item else None

    def get_user_by_username(self, username):
        user_item = self.dynamo.get_user_by_username(username)
        return self.init_user(user_item) if user_item else None

    def init_user(self, user_item):
        kwargs = {
            'block_manager': getattr(self, 'block_manager', None),
            'follow_manager': getattr(self, 'follow_manager', None),
            'post_manager': getattr(self, 'post_manager', None),
            'trending_manager': getattr(self, 'trending_manager', None),
        }
        return User(user_item, self.clients, **kwargs) if user_item else None

    def get_available_placeholder_photo_codes(self):
        # don't want to foce the test suite to always pass in this parameter
        if not self.placeholder_photos_directory:
            return []
        paths = self.s3_placeholder_photos_client.list_common_prefixes(self.placeholder_photos_directory + '/')
        return [path.split('/')[-2] for path in paths]

    def get_random_placeholder_photo_code(self):
        codes = self.get_available_placeholder_photo_codes()
        return random.choice(codes) if codes else None

    def create_cognito_only_user(self, user_id, username, full_name=None):
        # try to claim the new username, will raise an validation exception if already taken
        self.validate.username(username)
        full_name = None if full_name == '' else full_name  # treat empty string like null

        try:
            attrs = self.cognito_client.get_user_attributes(user_id)
        except self.cognito_client.boto_client.exceptions.UserNotFoundException:
            raise self.exceptions.UserValidationException(
                f'No entry found in cognito user pool with cognito username `{user_id}`'
            )
        email = attrs.get('email') if attrs.get('email_verified', 'false') == 'true' else None
        phone = attrs.get('phone_number') if attrs.get('phone_number_verified', 'false') == 'true' else None
        preferred_username = attrs.get('preferred_username', None)

        # set the lowercased version of username in cognito
        # this is part of allowing case-insensitive logins
        try:
            self.cognito_client.set_user_attributes(user_id, {'preferred_username': username.lower()})
        except self.cognito_client.boto_client.exceptions.AliasExistsException:
            raise self.exceptions.UserValidationException(
                f'Username `{username}` already taken (case-insensitive comparison)'
            )

        # create new user in the DB, have them follow the real user if they exist
        photo_code = self.get_random_placeholder_photo_code()
        try:
            item = self.dynamo.add_user(user_id, username, full_name=full_name, email=email, phone=phone,
                                        placeholder_photo_code=photo_code)
        except self.exceptions.UserAlreadyExists:
            # un-claim the username in cognito
            if preferred_username:
                self.cognito_client.set_user_attributes(user_id, {'preferred_username': preferred_username})
            else:
                self.cognito_client.clear_user_attribute(user_id, 'preferred_username')
            raise

        user = self.init_user(item)
        self.follow_real_user(user)
        return user

    def create_facebook_user(self, user_id, username, facebook_access_token, full_name=None):
        # do operations that do not alter state first
        self.validate.username(username)
        full_name = None if full_name == '' else full_name  # treat empty string like null

        email = self.facebook_client.get_verified_email(facebook_access_token).lower()
        if not email:
            raise self.exceptions.UserValidationException('Unable to retrieve email with that token')

        # set the user up in cognito, claims the username at the same time
        try:
            cognito_id_token = self.cognito_client.create_user_pool_entry(user_id, email, username)
            self.cognito_client.link_identity_pool_entries(user_id, cognito_id_token=cognito_id_token,
                                                           facebook_access_token=facebook_access_token)
        except (self.cognito_client.boto_client.exceptions.AliasExistsException,
                self.cognito_client.boto_client.exceptions.UsernameExistsException):
            raise self.exceptions.UserValidationException(
                f'Entry already exists cognito user pool with that cognito username `{user_id}` or email `{email}`'
            )

        # create new user in the DB, have them follow the real user if they exist
        photo_code = self.get_random_placeholder_photo_code()
        item = self.dynamo.add_user(user_id, username, full_name=full_name, email=email,
                                    placeholder_photo_code=photo_code)
        user = self.init_user(item)
        self.follow_real_user(user)
        return user

    def create_google_user(self, user_id, username, google_id_token, full_name=None):
        # do operations that do not alter state first
        self.validate.username(username)
        full_name = None if full_name == '' else full_name  # treat empty string like null

        try:
            email = self.google_client.get_verified_email(google_id_token).lower()
        except ValueError as err:
            msg = f'Unable to extract verified email from google id token: {err}'
            logger.warning(msg)
            raise self.exceptions.UserValidationException(msg)

        # set the user up in cognito
        try:
            cognito_id_token = self.cognito_client.create_user_pool_entry(user_id, email, username)
            self.cognito_client.link_identity_pool_entries(user_id, cognito_id_token=cognito_id_token,
                                                           google_id_token=google_id_token)
        except (self.cognito_client.boto_client.exceptions.AliasExistsException,
                self.cognito_client.boto_client.exceptions.UsernameExistsException):
            raise self.exceptions.UserValidationException(
                f'Entry already exists cognito user pool with that cognito username `{user_id}` or email `{email}`'
            )

        # create new user in the DB, have them follow the real user if they exist
        photo_code = self.get_random_placeholder_photo_code()
        item = self.dynamo.add_user(user_id, username, full_name=full_name, email=email,
                                    placeholder_photo_code=photo_code)
        user = self.init_user(item)
        self.follow_real_user(user)
        return user

    def follow_real_user(self, user):
        real_user = self.get_user_by_username('real')
        if real_user and real_user.id != user.id:
            self.follow_manager.request_to_follow(user, real_user)

    def get_text_tags(self, text):
        """
        Given a fragment of text, return a list of objects of form
            {'tag': '@username', 'userId': '...'}
        representing all the users tagged in the text.
        """
        username_tags = set(re.findall(self.username_tag_regex, text))
        # note that dynamo does not support batch gets using GSI's, and the username is in a GSI
        text_tags = []
        for tag in username_tags:
            user_item = self.dynamo.get_user_by_username(tag[1:])
            if user_item:
                text_tags.append({'tag': tag, 'userId': user_item['userId']})
        return text_tags
