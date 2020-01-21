import logging
import os

from app.models.media.enums import MediaSize, MediaExt

from . import enums, exceptions
from .dynamo import UserDynamo
from .validate import UserValidate

logger = logging.getLogger()

PLACEHOLDER_PHOTOS_DIRECTORY = os.environ.get('PLACEHOLDER_PHOTOS_DIRECTORY')
PLACEHOLDER_PHOTOS_CLOUDFRONT_DOMAIN = os.environ.get('PLACEHOLDER_PHOTOS_CLOUDFRONT_DOMAIN')

# annoying this needs to exist
CONTACT_ATTRIBUTE_NAMES = {
    'email': {
        'short': 'email',
        'cognito': 'email',
        'dynamo': 'email',
    },
    'phone': {
        'short': 'phone',
        'cognito': 'phone_number',
        'dynamo': 'phoneNumber',
    },
}


class User:

    enums = enums
    exceptions = exceptions
    client_names = ['cloudfront', 'cognito', 'dynamo', 's3_uploads']
    photo_file_ext = MediaExt.JPG

    def __init__(self, user_item, clients, follow_manager=None, trending_manager=None,
                 placeholder_photos_directory=PLACEHOLDER_PHOTOS_DIRECTORY,
                 placeholder_photos_cloudfront_domain=PLACEHOLDER_PHOTOS_CLOUDFRONT_DOMAIN):
        self.clients = clients
        for client_name in self.client_names:
            if client_name in clients:
                setattr(self, f'{client_name}_client', clients[client_name])
        if 'dynamo' in clients:
            self.dynamo = UserDynamo(clients['dynamo'])
        if follow_manager:
            self.follow_manager = follow_manager
        if trending_manager:
            self.trending_manager = trending_manager
        self.validate = UserValidate()
        self.item = user_item
        self.id = user_item['userId']
        self.placeholder_photos_directory = placeholder_photos_directory
        self.placeholder_photos_cloudfront_domain = placeholder_photos_cloudfront_domain

    def get_photo_path(self, size, photo_media_id=None):
        photo_media_id = photo_media_id or self.item.get('photoMediaId')
        if not photo_media_id:
            return None
        filename = f'{size}.{self.photo_file_ext}'
        return '/'.join([self.id, 'profile-photo', photo_media_id, filename])

    def get_placeholder_photo_path(self, size):
        code = self.item.get('placeholderPhotoCode')
        if not code or not self.placeholder_photos_directory:
            return None
        filename = f'{size}.{self.photo_file_ext}'
        return '/'.join([self.placeholder_photos_directory, code, filename])

    def get_photo_url(self, size):
        photo_path = self.get_photo_path(size)
        if photo_path:
            return self.cloudfront_client.generate_presigned_url(photo_path, ['GET', 'HEAD'])
        placeholder_path = self.get_placeholder_photo_path(size)
        if placeholder_path and self.placeholder_photos_cloudfront_domain:
            return f'https://{self.placeholder_photos_cloudfront_domain}/{placeholder_path}'
        return None

    def refresh_item(self):
        self.item = self.dynamo.get_user(self.id)
        return self

    def serialize(self):
        return self.item

    def set_accepted_eula_version(self, version):
        if version == self.item.get('acceptedEULAVersion'):
            return self
        self.item = self.dynamo.set_user_accepted_eula_version(self.id, version)
        return self

    def set_privacy_status(self, privacy_status):
        old_privacy_status = self.item.get('privacyStatus')
        if privacy_status == old_privacy_status:
            return self

        # are we changing from private to public?
        if old_privacy_status == enums.UserPrivacyStatus.PRIVATE and privacy_status == enums.UserPrivacyStatus.PUBLIC:
            self.follow_manager.accept_all_requested_follow_requests(self.id)
            self.follow_manager.delete_all_denied_follow_requests(self.id)

        self.item = self.dynamo.set_user_privacy_status(self.id, privacy_status)
        return self

    def update_username(self, username):
        old_username = self.item['username']
        if old_username == username:
            # no change was requested
            return self

        # validate and claim the lowercased username in cognito
        self.validate.username(username)
        try:
            self.cognito_client.set_user_attributes(self.id, {'preferred_username': username.lower()})
        except self.cognito_client.boto_client.exceptions.AliasExistsException:
            raise self.exceptions.UserValidationException(
                f'Username `{username}` already taken (case-insensitive comparison)'
            )

        self.item = self.dynamo.update_user_username(self.id, username, old_username)
        return self

    def update_photo(self, media):
        old_media_id = self.item.get('photoMediaId')
        new_media_id = media.id if media else None
        if new_media_id == old_media_id:
            return self

        # add the new s3 objects
        if new_media_id:
            self.add_photo_s3_objects(media)

        # then dynamo
        self.item = self.dynamo.set_user_photo_media_id(self.id, new_media_id)

        # delete the old s3 objects
        if old_media_id:
            self.delete_photo_s3_objects(photo_media_id=old_media_id)

        return self

    def add_photo_s3_objects(self, media):
        for size in MediaSize._ALL:
            source_path = media.get_s3_path(size)
            dest_path = self.get_photo_path(size, photo_media_id=media.id)
            self.s3_uploads_client.copy_object(source_path, dest_path)

    def update_details(self, full_name=None, bio=None, language_code=None, theme_code=None,
                       follow_counts_hidden=None, view_counts_hidden=None,
                       comments_disabled=None, likes_disabled=None, verification_hidden=None):
        "To delete a detail, set it to the empty string. Ex: `full_name=''`"
        kwargs = {}

        if full_name is not None and full_name != self.item.get('fullName'):
            kwargs['full_name'] = full_name

        if bio is not None and bio != self.item.get('bio'):
            kwargs['bio'] = bio

        if language_code is not None and language_code != self.item.get('languageCode', 'en'):
            kwargs['language_code'] = language_code

        if theme_code is not None and theme_code != self.item.get('themeCode', 'black.white'):
            kwargs['theme_code'] = theme_code

        if follow_counts_hidden is not None and follow_counts_hidden != self.item.get('followCountsHidden', False):
            kwargs['follow_counts_hidden'] = follow_counts_hidden

        if view_counts_hidden is not None and view_counts_hidden != self.item.get('viewCountsHidden', False):
            kwargs['view_counts_hidden'] = view_counts_hidden

        if comments_disabled is not None and comments_disabled != self.item.get('commentsDisabled', False):
            kwargs['comments_disabled'] = comments_disabled

        if likes_disabled is not None and likes_disabled != self.item.get('likesDisabled', False):
            kwargs['likes_disabled'] = likes_disabled

        if verification_hidden is not None and verification_hidden != self.item.get('verificationHidden', False):
            kwargs['verification_hidden'] = verification_hidden

        if kwargs:
            self.item = self.dynamo.set_user_details(self.id, **kwargs)
        return self

    def delete_photo_s3_objects(self, photo_media_id=None):
        for size in MediaSize._ALL:
            path = self.get_photo_path(size, photo_media_id=photo_media_id)
            self.s3_uploads_client.delete_object(path)

    def delete(self):
        """
        Delete the user item and resources it directly owns (ie profile photo) from stateful services.
        Return the dynamo item as it was before the delete.
        """
        # remove our trending item, if it's there
        self.trending_manager.dynamo.delete_trending(self.id)

        # delete our profile photo, if we have one
        if 'photoMediaId' in self.item:
            self.delete_photo_s3_objects()

        # release our preferred_username from cognito
        try:
            self.cognito_client.clear_user_attribute(self.id, 'preferred_username')
        except self.cognito_client.boto_client.exceptions.UserNotFoundException:
            logger.warning(f'No cognito user pool entry found when deleting user `{self.id}`')

        # delete our own profile
        item = self.dynamo.delete_user(self.id)
        self.item = None
        self.id = None
        return item

    def start_change_contact_attribute(self, attribute_name, attribute_value):
        assert attribute_name in CONTACT_ATTRIBUTE_NAMES
        names = CONTACT_ATTRIBUTE_NAMES[attribute_name]

        # verify we actually need to do anything
        old_value = self.item.get(names['dynamo'])
        if old_value == attribute_value:
            raise exceptions.UserVerificationException(f'User {attribute_name} is already set to `{attribute_value}`')

        # first we set the users email to the new, unverified one, while also setting it to another property
        # this sends the verification email to the user
        attrs = {
            names['cognito']: attribute_value,
            f'custom:unverified_{names["short"]}': attribute_value,
        }
        self.cognito_client.set_user_attributes(self.id, attrs)

        # then if we have a verified version for the user stored in dynamo, set their main property in
        # cognito *back* to their verified version. This allows them to still use it to login.
        if old_value:
            attrs = {
                names['cognito']: old_value,
                f'{names["cognito"]}_verified': 'true',
            }
            self.cognito_client.set_user_attributes(self.id, attrs)
        return self

    def finish_change_contact_attribute(self, attribute_name, access_token, verification_code):
        assert attribute_name in CONTACT_ATTRIBUTE_NAMES
        names = CONTACT_ATTRIBUTE_NAMES[attribute_name]

        # first, figure out what that the value we're validating is
        user_attrs = self.cognito_client.get_user_attributes(self.id)
        value = user_attrs.get(f'custom:unverified_{names["short"]}')
        if not value:
            raise exceptions.UserVerificationException(f'No unverified email found to validate for user `{self.id}`')

        # try to do the validation
        try:
            self.cognito_client.verify_user_attribute(access_token, names['cognito'], verification_code)
        except self.cognito_client.boto_client.exceptions.CodeMismatchException:
            raise exceptions.UserVerificationException('Verification code is invalid')

        # success, update cognito, dynamo, then delete the temporary attribute in cognito
        attrs = {
            names['cognito']: value,
            f'{names["cognito"]}_verified': 'true',
        }
        self.cognito_client.set_user_attributes(self.id, attrs)
        self.item = self.dynamo.set_user_details(self.id, **{names['short']: value})
        self.cognito_client.clear_user_attribute(self.id, f'custom:unverified_{names["short"]}')
        return self
