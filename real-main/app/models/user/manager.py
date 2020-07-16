import logging
import os
import random
import re
from functools import partialmethod

from app import models
from app.mixins.base import ManagerBase
from app.mixins.trending.manager import TrendingManagerMixin
from app.models.card.specs import ChatCardSpec, RequestedFollowersCardSpec
from app.utils import GqlNotificationType

from .dynamo import UserDynamo
from .enums import UserStatus
from .exceptions import UserAlreadyExists, UserValidationException
from .model import User
from .validate import UserValidate

logger = logging.getLogger()

S3_PLACEHOLDER_PHOTOS_DIRECTORY = os.environ.get('S3_PLACEHOLDER_PHOTOS_DIRECTORY')


class UserManager(TrendingManagerMixin, ManagerBase):

    client_names = [
        'apple',
        'appsync',
        'cloudfront',
        'cognito',
        'elasticsearch',
        'dynamo',
        'facebook',
        'google',
        'pinpoint',
        's3_uploads',
        's3_placeholder_photos',
    ]
    username_tag_regex = re.compile('@' + UserValidate.username_regex.pattern)
    item_type = 'user'

    def __init__(self, clients, managers=None, placeholder_photos_directory=S3_PLACEHOLDER_PHOTOS_DIRECTORY):
        super().__init__(clients, managers=managers)
        managers = managers or {}
        managers['user'] = self
        self.album_manager = managers.get('album') or models.AlbumManager(clients, managers=managers)
        self.block_manager = managers.get('block') or models.BlockManager(clients, managers=managers)
        self.card_manager = managers.get('card') or models.CardManager(clients, managers=managers)
        self.chat_manager = managers.get('chat') or models.ChatManager(clients, managers=managers)
        self.comment_manager = managers.get('comment') or models.CommentManager(clients, managers=managers)
        self.follower_manager = managers.get('follower') or models.FollowerManager(clients, managers=managers)
        self.like_manager = managers.get('like') or models.LikeManager(clients, managers=managers)
        self.post_manager = managers.get('post') or models.PostManager(clients, managers=managers)

        self.clients = clients
        for client_name in self.client_names:
            if client_name in clients:
                setattr(self, f'{client_name}_client', clients[client_name])
        if 'dynamo' in clients:
            self.dynamo = UserDynamo(clients['dynamo'])
        self.validate = UserValidate()
        self.placeholder_photos_directory = placeholder_photos_directory

    @property
    def real_user_id(self):
        "The userId of the 'real' user, if they exist"
        if not hasattr(self, '_real_user_id'):
            real_user = self.get_user_by_username('real')
            self._real_user_id = real_user.id if real_user else None
        return self._real_user_id

    def get_user(self, user_id, strongly_consistent=False):
        user_item = self.dynamo.get_user(user_id, strongly_consistent=strongly_consistent)
        return self.init_user(user_item) if user_item else None

    def get_user_by_username(self, username):
        user_item = self.dynamo.get_user_by_username(username)
        return self.init_user(user_item) if user_item else None

    def init_user(self, user_item):
        kwargs = {
            'trending_dynamo': getattr(self, 'trending_dynamo', None),
            'album_manager': getattr(self, 'album_manager', None),
            'block_manager': getattr(self, 'block_manager', None),
            'card_manager': getattr(self, 'card_manager', None),
            'chat_manager': getattr(self, 'chat_manager', None),
            'comment_manager': getattr(self, 'comment_manager', None),
            'follower_manager': getattr(self, 'follower_manager', None),
            'like_manager': getattr(self, 'like_manager', None),
            'post_manager': getattr(self, 'post_manager', None),
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
        except self.cognito_client.user_pool_client.exceptions.UserNotFoundException:
            raise UserValidationException(
                f'No entry found in cognito user pool with cognito username `{user_id}`'
            )
        preferred_username = attrs.get('preferred_username', None)
        email = attrs.get('email') if attrs.get('email_verified', 'false') == 'true' else None
        phone = attrs.get('phone_number') if attrs.get('phone_number_verified', 'false') == 'true' else None
        if not email and not phone:
            raise UserValidationException(f'User `{user_id}` has neither verified email nor phone')

        # set the lowercased version of username in cognito
        # this is part of allowing case-insensitive logins
        try:
            self.cognito_client.set_user_attributes(user_id, {'preferred_username': username.lower()})
        except self.cognito_client.user_pool_client.exceptions.AliasExistsException:
            raise UserValidationException(f'Username `{username}` already taken (case-insensitive comparison)')

        # create new user in the DB, have them follow the real user if they exist
        photo_code = self.get_random_placeholder_photo_code()
        try:
            item = self.dynamo.add_user(
                user_id,
                username,
                full_name=full_name,
                email=email,
                phone=phone,
                placeholder_photo_code=photo_code,
            )
        except UserAlreadyExists:
            # un-claim the username in cognito
            if preferred_username:
                self.cognito_client.set_user_attributes(user_id, {'preferred_username': preferred_username})
            else:
                self.cognito_client.clear_user_attribute(user_id, 'preferred_username')
            raise

        user = self.init_user(item)
        self.follow_real_user(user)
        return user

    def create_federated_user(self, provider, user_id, username, token, full_name=None):
        assert provider in ('apple', 'facebook', 'google'), f'Unrecognized identity provider `{provider}`'
        provider_client = self.clients[provider]

        # do operations that do not alter state first
        self.validate.username(username)
        full_name = None if full_name == '' else full_name  # treat empty string like null

        try:
            email = provider_client.get_verified_email(token).lower()
        except ValueError as err:
            logger.warning(str(err))
            raise UserValidationException(str(err))

        # set the user up in cognito, claims the username at the same time
        try:
            self.cognito_client.create_verified_user_pool_entry(user_id, username, email)
            tokens = {
                'cognito_token': self.cognito_client.get_user_pool_id_token(user_id),
                provider + '_token': token,
            }
            self.cognito_client.link_identity_pool_entries(user_id, **tokens)
        except (
            self.cognito_client.user_pool_client.exceptions.AliasExistsException,
            self.cognito_client.user_pool_client.exceptions.UsernameExistsException,
        ):
            raise UserValidationException(
                f'Entry already exists cognito user pool with that cognito username `{user_id}` or email `{email}`'
            )

        # create new user in the DB, have them follow the real user if they exist
        photo_code = self.get_random_placeholder_photo_code()
        item = self.dynamo.add_user(
            user_id, username, full_name=full_name, email=email, placeholder_photo_code=photo_code
        )
        user = self.init_user(item)
        self.follow_real_user(user)
        return user

    def follow_real_user(self, user):
        real_user = self.get_user_by_username('real')
        if real_user and real_user.id != user.id:
            self.follower_manager.request_to_follow(user, real_user)

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

    def on_comment_add(self, comment_id, new_item):
        self.dynamo.increment_comment_count(new_item['userId'])

    def on_comment_delete(self, comment_id, old_item):
        user_id = old_item['userId']
        self.dynamo.decrement_comment_count(user_id, fail_soft=True)
        self.dynamo.increment_comment_deleted_count(user_id)

    def on_card_add(self, card_id, new_item):
        card = self.card_manager.init_card(new_item)
        self.dynamo.increment_card_count(card.user_id)

    def on_card_delete(self, card_id, old_item):
        card = self.card_manager.init_card(old_item)
        self.dynamo.decrement_card_count(card.user_id, fail_soft=True)

    def on_user_delete(self, user_id, old_item):
        self.elasticsearch_client.delete_user(user_id)
        self.pinpoint_client.delete_user_endpoints(user_id)

    def sync_user_status_due_to(self, check_method_name, forced_by, user_id, new_item, old_item=None):
        user = self.init_user(new_item)
        if getattr(user, check_method_name)():
            user.disable(forced_by=forced_by)

    sync_user_status_due_to_chat_messages = partialmethod(
        sync_user_status_due_to, 'is_forced_disabling_criteria_met_by_chat_messages', 'chatMessages'
    )
    sync_user_status_due_to_comments = partialmethod(
        sync_user_status_due_to, 'is_forced_disabling_criteria_met_by_comments', 'comments'
    )
    sync_user_status_due_to_posts = partialmethod(
        sync_user_status_due_to, 'is_forced_disabling_criteria_met_by_posts', 'posts'
    )

    def sync_card_with_count(self, dynamo_attr, card_spec_class, user_id, new_item, old_item=None):
        cnt = new_item.get(dynamo_attr, 0)
        card_spec = card_spec_class(user_id, cnt)
        if cnt > 0:
            self.card_manager.add_or_update_card_by_spec(card_spec)
        else:
            self.card_manager.remove_card_by_spec_if_exists(card_spec)

    sync_requested_followers_card = partialmethod(
        sync_card_with_count, 'followersRequestedCount', RequestedFollowersCardSpec
    )
    sync_chats_with_new_messages_card = partialmethod(
        sync_card_with_count, 'chatsWithUnviewedMessagesCount', ChatCardSpec
    )

    def sync_elasticsearch(self, user_id, new_item, old_item=None):
        self.elasticsearch_client.put_user(user_id, new_item['username'], new_item.get('fullName'))

    def sync_pinpoint_attribute(self, dynamo_name, pinpoint_name, user_id, new_item, old_item=None):
        value = new_item.get(dynamo_name)
        if value is not None:
            self.pinpoint_client.update_user_endpoint(user_id, pinpoint_name, value)
        else:
            self.pinpoint_client.delete_user_endpoint(user_id, pinpoint_name)

    sync_pinpoint_email = partialmethod(sync_pinpoint_attribute, 'email', 'EMAIL')
    sync_pinpoint_phone = partialmethod(sync_pinpoint_attribute, 'phoneNumber', 'SMS')

    def sync_pinpoint_user_status(self, user_id, new_item, old_item=None):
        status = new_item.get('userStatus', UserStatus.ACTIVE)
        if status == UserStatus.ACTIVE:
            self.pinpoint_client.enable_user_endpoints(user_id)
        if status == UserStatus.DISABLED:
            self.pinpoint_client.disable_user_endpoints(user_id)
        if status == UserStatus.DELETING:
            self.pinpoint_client.delete_user_endpoints(user_id)

    def sync_chats_with_unviewed_messages_count(self, chat_id, new_item=None, old_item=None):
        "Sync User.chatsWithUnviewedMessagesCount to changes to chat member items"
        # digging kinda deep into the chat member object from here... should probably make a ChatMember class
        user_id = (new_item or old_item)['sortKey'].split('/')[1]
        new_count = (new_item or {}).get('messagesUnviewedCount', 0)
        old_count = (old_item or {}).get('messagesUnviewedCount', 0)
        if old_count == 0 and new_count > 0:
            self.dynamo.increment_chats_with_unviewed_messages_count(user_id)
        if old_count > 0 and new_count == 0:
            self.dynamo.decrement_chats_with_unviewed_messages_count(user_id, fail_soft=True)

    def fire_gql_subscription_chats_with_unviewed_messages_count(self, user_id, new_item, old_item=None):
        self.appsync_client.fire_notification(
            user_id,
            GqlNotificationType.USER_CHATS_WITH_UNVIEWED_MESSAGES_COUNT_CHANGED,
            userChatsWithUnviewedMessagesCount=int(new_item.get('chatsWithUnviewedMessagesCount', 0)),
        )
