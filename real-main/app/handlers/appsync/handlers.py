import logging
import os

import pendulum

from app.clients import (AppSyncClient, CloudFrontClient, CognitoClient, DynamoClient, FacebookClient, GoogleClient,
                         PostVerificationClient, SecretsManagerClient, S3Client)
from app.models.album import AlbumManager
from app.models.block import BlockManager
from app.models.chat import ChatManager
from app.models.chat_message import ChatMessageManager
from app.models.comment import CommentManager
from app.models.flag import FlagManager
from app.models.follow import FollowManager
from app.models.follow.enums import FollowStatus
from app.models.followed_first_story import FollowedFirstStoryManager
from app.models.like import LikeManager
from app.models.like.enums import LikeStatus
from app.models.media import MediaManager
from app.models.post import PostManager
from app.models.post.enums import PostStatus, PostType
from app.models.user import UserManager
from app.models.view import ViewManager
from app.utils import image_size

from . import routes
from .exceptions import ClientException

S3_UPLOADS_BUCKET = os.environ.get('S3_UPLOADS_BUCKET')
S3_PLACEHOLDER_PHOTOS_BUCKET = os.environ.get('S3_PLACEHOLDER_PHOTOS_BUCKET')

logger = logging.getLogger()

secrets_manager_client = SecretsManagerClient()
clients = {
    'appsync': AppSyncClient(),
    'cloudfront': CloudFrontClient(secrets_manager_client.get_cloudfront_key_pair),
    'cognito': CognitoClient(),
    'dynamo': DynamoClient(),
    'facebook': FacebookClient(),
    'google': GoogleClient(secrets_manager_client.get_google_client_ids),
    'post_verification': PostVerificationClient(secrets_manager_client.get_post_verification_api_creds),
    's3_uploads': S3Client(S3_UPLOADS_BUCKET),
    's3_placeholder_photos': S3Client(S3_PLACEHOLDER_PHOTOS_BUCKET),
}

# shared hash of all managers, allows inter-manager communication
managers = {}
album_manager = managers.get('album') or AlbumManager(clients, managers=managers)
block_manager = managers.get('block') or BlockManager(clients, managers=managers)
chat_manager = managers.get('chat') or ChatManager(clients, managers=managers)
chat_message_manager = managers.get('chat_message') or ChatMessageManager(clients, managers=managers)
comment_manager = managers.get('comment') or CommentManager(clients, managers=managers)
ffs_manager = managers.get('followed_first_story') or FollowedFirstStoryManager(clients, managers=managers)
flag_manager = managers.get('flag') or FlagManager(clients, managers=managers)
follow_manager = managers.get('follow') or FollowManager(clients, managers=managers)
like_manager = managers.get('like') or LikeManager(clients, managers=managers)
media_manager = managers.get('media') or MediaManager(clients, managers=managers)
post_manager = managers.get('post') or PostManager(clients, managers=managers)
user_manager = managers.get('user') or UserManager(clients, managers=managers)
view_manager = managers.get('view') or ViewManager(clients, managers=managers)


@routes.register('Mutation.createCognitoOnlyUser')
def create_cognito_only_user(caller_user_id, arguments, source, context):
    username = arguments['username']
    full_name = arguments.get('fullName')
    try:
        user = user_manager.create_cognito_only_user(caller_user_id, username, full_name=full_name)
    except user_manager.exceptions.UserException as err:
        raise ClientException(str(err))
    return user.serialize(caller_user_id)


@routes.register('Mutation.createFacebookUser')
def create_facebook_user(caller_user_id, arguments, source, context):
    username = arguments['username']
    full_name = arguments.get('fullName')
    facebook_token = arguments['facebookAccessToken']
    try:
        user = user_manager.create_facebook_user(caller_user_id, username, facebook_token, full_name=full_name)
    except user_manager.exceptions.UserException as err:
        raise ClientException(str(err))
    return user.serialize(caller_user_id)


@routes.register('Mutation.createGoogleUser')
def create_google_user(caller_user_id, arguments, source, context):
    username = arguments['username']
    full_name = arguments.get('fullName')
    google_id_token = arguments['googleIdToken']
    try:
        user = user_manager.create_google_user(caller_user_id, username, google_id_token, full_name=full_name)
    except user_manager.exceptions.UserException as err:
        raise ClientException(str(err))
    return user.serialize(caller_user_id)


@routes.register('Mutation.startChangeUserEmail')
def start_change_user_email(caller_user_id, arguments, source, context):
    email = arguments['email']
    user = user_manager.get_user(caller_user_id)
    try:
        user.start_change_contact_attribute('email', email)
    except user_manager.exceptions.UserException as err:
        raise ClientException(str(err))
    return user.serialize(caller_user_id)


@routes.register('Mutation.finishChangeUserEmail')
def finish_change_user_email(caller_user_id, arguments, source, context):
    access_token = arguments['cognitoAccessToken']
    code = arguments['verificationCode']
    user = user_manager.get_user(caller_user_id)
    try:
        user.finish_change_contact_attribute('email', access_token, code)
    except user_manager.exceptions.UserException as err:
        raise ClientException(str(err))
    return user.serialize(caller_user_id)


@routes.register('Mutation.startChangeUserPhoneNumber')
def start_change_user_phone_number(caller_user_id, arguments, source, context):
    phone = arguments['phoneNumber']
    user = user_manager.get_user(caller_user_id)
    try:
        user.start_change_contact_attribute('phone', phone)
    except user_manager.exceptions.UserException as err:
        raise ClientException(str(err))
    return user.serialize(caller_user_id)


@routes.register('Mutation.finishChangeUserPhoneNumber')
def finish_change_user_phone_number(caller_user_id, arguments, source, context):
    access_token = arguments['cognitoAccessToken']
    code = arguments['verificationCode']
    user = user_manager.get_user(caller_user_id)
    try:
        user.finish_change_contact_attribute('phone', access_token, code)
    except user_manager.exceptions.UserException as err:
        raise ClientException(str(err))
    return user.serialize(caller_user_id)


@routes.register('Mutation.setUserDetails')
def set_user_details(caller_user_id, arguments, source, context):
    username = arguments.get('username')
    full_name = arguments.get('fullName')
    bio = arguments.get('bio')
    photo_post_id = arguments.get('photoPostId')
    privacy_status = arguments.get('privacyStatus')
    follow_counts_hidden = arguments.get('followCountsHidden')
    view_counts_hidden = arguments.get('viewCountsHidden')
    language_code = arguments.get('languageCode')
    theme_code = arguments.get('themeCode')
    comments_disabled = arguments.get('commentsDisabled')
    likes_disabled = arguments.get('likesDisabled')
    sharing_disabled = arguments.get('sharingDisabled')
    verification_hidden = arguments.get('verificationHidden')

    args = (
        username, full_name, bio, photo_post_id, privacy_status, follow_counts_hidden,
        language_code, theme_code, comments_disabled, likes_disabled, sharing_disabled, verification_hidden,
        view_counts_hidden,
    )
    if all(v is None for v in args):
        raise ClientException('Called without any arguments... probably not what you intended?')

    user = user_manager.get_user(caller_user_id)
    if not user:
        raise ClientException(f'User `{caller_user_id}` does not exist')

    # are we claiming a new username?
    if username is not None:
        try:
            user = user.update_username(username)
        except user_manager.exceptions.UserException as err:
            raise ClientException(str(err))

    # are we setting a new profile picture?
    if photo_post_id is not None:
        post_id = photo_post_id if photo_post_id != '' else None
        try:
            user.update_photo(post_id)
        except user_manager.exceptions.UserException as err:
            raise ClientException(str(err))

    # are we changing our privacy status?
    if privacy_status is not None:
        user.set_privacy_status(privacy_status)

    # update the simple properties
    user.update_details(
        full_name=full_name,
        bio=bio,
        language_code=language_code,
        theme_code=theme_code,
        follow_counts_hidden=follow_counts_hidden,
        view_counts_hidden=view_counts_hidden,
        comments_disabled=comments_disabled,
        likes_disabled=likes_disabled,
        sharing_disabled=sharing_disabled,
        verification_hidden=verification_hidden,
    )
    return user.serialize(caller_user_id)


@routes.register('Mutation.setUserAcceptedEULAVersion')
def set_user_accepted_eula_version(caller_user_id, arguments, source, context):
    version = arguments['version']

    user = user_manager.get_user(caller_user_id)
    if not user:
        raise ClientException(f'User `{caller_user_id}` does not exist')

    # use the empty string to request deleting
    if version == '':
        version = None
    user.set_accepted_eula_version(version)
    return user.serialize(caller_user_id)


@routes.register('Mutation.resetUser')
def reset_user(caller_user_id, arguments, source, context):
    new_username = arguments.get('newUsername')
    new_username = None if new_username == '' else new_username  # treat empty string like null

    # for REQUESTED and DENIED, just delete them
    # for FOLLOWING, unfollow so that the other user's counts remain correct
    follow_manager.reset_followed_items(caller_user_id)
    follow_manager.reset_follower_items(caller_user_id)

    # unflag everything we've flagged
    flag_manager.unflag_all_by_user(caller_user_id)

    # delete all our likes & comments & albums
    like_manager.dislike_all_by_user(caller_user_id)
    comment_manager.delete_all_by_user(caller_user_id)
    album_manager.delete_all_by_user(caller_user_id)

    # delete all our posts, and all likes on those posts
    for post_item in post_manager.dynamo.generate_posts_by_user(caller_user_id):
        post_manager.init_post(post_item).delete()

    # remove all blocks of and by us
    block_manager.unblock_all_blocks(caller_user_id)

    # leave all chats we are part of (auto-deletes direct & solo chats)
    chat_manager.leave_all_chats(caller_user_id)

    # finally, delete our own profile
    user = user_manager.get_user(caller_user_id)
    user_item = user.delete() if user else None

    if not new_username:
        if user_item:
            user_item['blockerStatus'] = block_manager.enums.BlockStatus.SELF
            user_item['followedStatus'] = follow_manager.enums.FollowStatus.SELF
        return user_item

    # equivalent to calling Mutation.createCognitoOnlyUser()
    try:
        user = user_manager.create_cognito_only_user(caller_user_id, new_username)
    except user_manager.exceptions.UserException as err:
        raise ClientException(str(err))
    return user.serialize(caller_user_id)


@routes.register('User.photo')
def user_photo(caller_user_id, arguments, source, context):
    user = user_manager.init_user(source)
    native_url = user.get_photo_url(image_size.NATIVE)
    if not native_url:
        return None
    return {
        'url': native_url,
        'url64p': user.get_photo_url(image_size.P64),
        'url480p': user.get_photo_url(image_size.P480),
        'url1080p': user.get_photo_url(image_size.P1080),
        'url4k': user.get_photo_url(image_size.K4),
    }


@routes.register('Mutation.followUser')
def follow_user(caller_user_id, arguments, source, context):
    follower_user_id = caller_user_id
    followed_user_id = arguments['userId']

    if follower_user_id == followed_user_id:
        raise ClientException('User cannot follow themselves')

    follower_user = user_manager.get_user(follower_user_id)
    if not follower_user:
        raise ClientException(f'No user profile found for follower `{follower_user_id}`')

    followed_user = user_manager.get_user(followed_user_id)
    if not followed_user:
        raise ClientException(f'No user profile found for followed `{followed_user_id}`')

    try:
        follow = follow_manager.request_to_follow(follower_user, followed_user)
    except follow_manager.exceptions.FollowException as err:
        raise ClientException(str(err))

    resp = followed_user.serialize(caller_user_id)
    resp['followedStatus'] = follow.status
    if follow.status == FollowStatus.FOLLOWING:
        resp['followerCount'] = followed_user.item.get('followerCount', 0) + 1
    return resp


@routes.register('Mutation.unfollowUser')
def unfollow_user(caller_user_id, arguments, source, context):
    follower_user_id = caller_user_id
    followed_user_id = arguments['userId']

    follow = follow_manager.get_follow(follower_user_id, followed_user_id)
    if not follow:
        raise ClientException(f'User `{follower_user_id}` is not following `{followed_user_id}`')

    try:
        follow.unfollow()
    except follow_manager.exceptions.FollowException as err:
        raise ClientException(str(err))

    resp = user_manager.get_user(followed_user_id, strongly_consistent=True).serialize(caller_user_id)
    resp['followedStatus'] = follow.status
    return resp


@routes.register('Mutation.acceptFollowerUser')
def accept_follower_user(caller_user_id, arguments, source, context):
    followed_user_id = caller_user_id
    follower_user_id = arguments['userId']

    follow = follow_manager.get_follow(follower_user_id, followed_user_id)
    if not follow:
        raise ClientException(f'User `{follower_user_id}` has not requested to follow user `{followed_user_id}`')

    try:
        follow.accept()
    except follow_manager.exceptions.FollowException as err:
        raise ClientException(str(err))

    resp = user_manager.get_user(follower_user_id, strongly_consistent=True).serialize(caller_user_id)
    resp['followerStatus'] = follow.status
    return resp


@routes.register('Mutation.denyFollowerUser')
def deny_follower_user(caller_user_id, arguments, source, context):
    followed_user_id = caller_user_id
    follower_user_id = arguments['userId']

    follow = follow_manager.get_follow(follower_user_id, followed_user_id)
    if not follow:
        raise ClientException(f'User `{follower_user_id}` has not requested to follow user `{followed_user_id}`')

    try:
        follow.deny()
    except follow_manager.exceptions.FollowException as err:
        raise ClientException(str(err))

    resp = user_manager.get_user(follower_user_id, strongly_consistent=True).serialize(caller_user_id)
    resp['followerStatus'] = follow.status
    return resp


@routes.register('Mutation.blockUser')
def block_user(caller_user_id, arguments, source, context):
    blocker_user_id = caller_user_id
    blocked_user_id = arguments['userId']

    if blocker_user_id == blocked_user_id:
        raise ClientException('Cannot block yourself')

    blocker_user = user_manager.get_user(blocker_user_id)
    if not blocker_user:
        raise ClientException(f'User `{blocker_user_id}` does not exist')

    blocked_user = user_manager.get_user(blocked_user_id)
    if not blocked_user:
        raise ClientException(f'User `{blocked_user_id}` does not exist')

    try:
        block_manager.block(blocker_user, blocked_user)
    except block_manager.exceptions.AlreadyBlocked as err:
        raise ClientException(str(err))

    resp = blocked_user.serialize(caller_user_id)
    resp['blockedStatus'] = block_manager.enums.BlockStatus.BLOCKING
    return resp


@routes.register('Mutation.unblockUser')
def unblock_user(caller_user_id, arguments, source, context):
    blocker_user_id = caller_user_id
    blocked_user_id = arguments['userId']

    if blocker_user_id == blocked_user_id:
        raise ClientException('Cannot unblock yourself')

    blocker_user = user_manager.get_user(blocker_user_id)
    if not blocker_user:
        raise ClientException(f'User `{blocker_user_id}` does not exist')

    blocked_user = user_manager.get_user(blocked_user_id)
    if not blocked_user:
        raise ClientException(f'User `{blocked_user_id}` does not exist')

    try:
        block_manager.unblock(blocker_user, blocked_user)
    except block_manager.exceptions.NotBlocked as err:
        raise ClientException(str(err))

    resp = blocked_user.serialize(caller_user_id)
    resp['blockedStatus'] = block_manager.enums.BlockStatus.NOT_BLOCKING
    return resp


@routes.register('Mutation.addPost')
def add_post(caller_user_id, arguments, source, context):
    user = user_manager.get_user(caller_user_id)
    if not user:
        raise ClientException(f'User `{caller_user_id}` does not exist')

    post_id = arguments['postId']
    post_type = arguments.get('postType') or PostType.IMAGE
    text = arguments.get('text')
    image_input = arguments.get('imageInput')
    album_id = arguments.get('albumId')

    media_uploads = arguments.get('mediaObjectUploads', [])
    if not image_input and media_uploads:
        if len(media_uploads) > 1:
            raise ClientException('Refusing to add post with more than one media')
        image_input = media_uploads[0]

    def argument_with_user_level_default(name):
        value = arguments.get(name)
        if value is not None:
            return value
        return user.item.get(name)

    # mental health settings: the user-level settings are defaults
    comments_disabled = argument_with_user_level_default('commentsDisabled')
    likes_disabled = argument_with_user_level_default('likesDisabled')
    sharing_disabled = argument_with_user_level_default('sharingDisabled')
    verification_hidden = argument_with_user_level_default('verificationHidden')

    lifetime_iso = arguments.get('lifetime')
    if lifetime_iso:
        try:
            lifetime_duration = pendulum.parse(lifetime_iso)
        except pendulum.exceptions.ParserError:
            raise ClientException(f'Unable to parse lifetime `{lifetime_iso}`')
        if not isinstance(lifetime_duration, pendulum.Duration):
            raise ClientException(f'Unable to parse lifetime `{lifetime_iso}` as duration')
    else:
        lifetime_duration = None

    org_post_count = user.item.get('postCount', 0)
    try:
        post = post_manager.add_post(
            user.id, post_id, post_type, image_input=image_input, text=text, lifetime_duration=lifetime_duration,
            album_id=album_id, comments_disabled=comments_disabled, likes_disabled=likes_disabled,
            sharing_disabled=sharing_disabled, verification_hidden=verification_hidden,
        )
    except post_manager.exceptions.PostException as err:
        raise ClientException(str(err))

    resp = post.serialize(caller_user_id)

    # if the posts was completed right away (ie a text-only post), then the user's postCount was incremented
    if post.status == PostStatus.COMPLETED:
        resp['postedBy']['postCount'] = org_post_count + 1

    return resp


@routes.register('Post.image')
def post_image(caller_user_id, arguments, source, context):
    post = post_manager.get_post(source['postId'])

    if not post or post.status == PostStatus.DELETING:
        return None

    if post.type == PostType.IMAGE:
        allowed_statuses = [media_manager.enums.MediaStatus.UPLOADED, media_manager.enums.MediaStatus.ARCHIVED]
        media_items = [
            mi for mi in media_manager.dynamo.generate_by_post(source['postId'])
            if mi['mediaStatus'] in allowed_statuses
        ]
        if media_items:
            media = media_manager.init_media(media_items[0])
            return {
                'url': post.get_image_readonly_url(image_size.NATIVE),
                'url64p': post.get_image_readonly_url(image_size.P64),
                'url480p': post.get_image_readonly_url(image_size.P480),
                'url1080p': post.get_image_readonly_url(image_size.P1080),
                'url4k': post.get_image_readonly_url(image_size.K4),
                'width': media.item.get('width'),
                'height': media.item.get('height'),
                'colors': media.item.get('colors'),
            }

    if post.type == PostType.VIDEO:
        if post.status in (PostStatus.COMPLETED, PostStatus.ARCHIVED):
            return {
                'url': post.get_image_readonly_url(image_size.NATIVE),
                'url64p': post.get_image_readonly_url(image_size.P64),
                'url480p': post.get_image_readonly_url(image_size.P480),
                'url1080p': post.get_image_readonly_url(image_size.P1080),
                'url4k': post.get_image_readonly_url(image_size.K4),
            }

    return None


@routes.register('Post.imageUploadUrl')
def post_image_upload_url(caller_user_id, arguments, source, context):
    post_id = source['postId']
    user_id = source['postedByUserId']

    if caller_user_id != user_id:
        return None

    post = post_manager.get_post(post_id)
    if not post or post.type != PostType.IMAGE or post.status != PostStatus.PENDING:
        return None

    return post.get_image_writeonly_url()


@routes.register('Post.video')
def post_video(caller_user_id, arguments, source, context):
    post = post_manager.get_post(source['postId'])

    statuses = (PostStatus.COMPLETED, PostStatus.ARCHIVED)
    if not post or post.type != PostType.VIDEO or post.status not in statuses:
        return None

    return {
        'urlMasterM3U8': post.get_hls_master_m3u8_url(),
        'accessCookies': post.get_hls_access_cookies(),
    }


@routes.register('Post.videoUploadUrl')
def post_video_upload_url(caller_user_id, arguments, source, context):
    post_id = source['postId']
    user_id = source['postedByUserId']

    if caller_user_id != user_id:
        return None

    post = post_manager.get_post(post_id)
    if not post or post.type != PostType.VIDEO or post.status != PostStatus.PENDING:
        return None

    return post.get_video_writeonly_url()


@routes.register('Mutation.editPost')
def edit_post(caller_user_id, arguments, source, context):
    post_id = arguments['postId']
    edit_kwargs = {
        'text': arguments.get('text'),
        'comments_disabled': arguments.get('commentsDisabled'),
        'likes_disabled': arguments.get('likesDisabled'),
        'sharing_disabled': arguments.get('sharingDisabled'),
        'verification_hidden': arguments.get('verificationHidden'),
    }

    post = post_manager.get_post(post_id)
    if not post:
        raise ClientException(f'Post `{post_id}` does not exist')

    if caller_user_id != post.user_id:
        raise ClientException("Cannot edit another User's post")

    try:
        post.set(**edit_kwargs)
    except post_manager.exceptions.PostException as err:
        raise ClientException(str(err))

    return post.serialize(caller_user_id)


@routes.register('Mutation.editPostAlbum')
def edit_post_album(caller_user_id, arguments, source, context):
    post_id = arguments['postId']
    album_id = arguments.get('albumId')

    post = post_manager.get_post(post_id)
    if not post:
        raise ClientException(f'Post `{post_id}` does not exist')

    if caller_user_id != post.user_id:
        raise ClientException("Cannot edit another user's post")

    try:
        post.set_album(album_id)
    except post_manager.exceptions.PostException as err:
        raise ClientException(str(err))

    return post.serialize(caller_user_id)


@routes.register('Mutation.editPostAlbumOrder')
def edit_post_album_order(caller_user_id, arguments, source, context):
    post_id = arguments['postId']
    preceding_post_id = arguments.get('precedingPostId')

    post = post_manager.get_post(post_id)
    if not post:
        raise ClientException(f'Post `{post_id}` does not exist')

    if caller_user_id != post.user_id:
        raise ClientException("Cannot edit another user's post")

    try:
        post.set_album_order(preceding_post_id)
    except post_manager.exceptions.PostException as err:
        raise ClientException(str(err))

    return post.serialize(caller_user_id)


@routes.register('Mutation.editPostExpiresAt')
def edit_post_expires_at(caller_user_id, arguments, source, context):
    post_id = arguments['postId']
    expires_at_str = arguments.get('expiresAt')
    expires_at = pendulum.parse(expires_at_str) if expires_at_str else None

    post = post_manager.get_post(post_id)
    if not post:
        raise ClientException(f'Post `{post_id}` does not exist')

    if caller_user_id != post.user_id:
        raise ClientException("Cannot edit another User's post")

    if expires_at and expires_at < pendulum.now('utc'):
        raise ClientException("Cannot set expiresAt to date time in the past: `{expires_at}`")

    post.set_expires_at(expires_at)
    return post.serialize(caller_user_id)


@routes.register('Mutation.flagPost')
def flag_post(caller_user_id, arguments, source, context):
    post_id = arguments['postId']

    post = post_manager.get_post(post_id)
    if not post:
        raise ClientException(f'Post `{post_id}` does not exist')

    try:
        post = flag_manager.flag_post(caller_user_id, post)
    except (flag_manager.exceptions.FlagException, post_manager.exceptions.PostException) as err:
        raise ClientException(str(err))

    resp = post.serialize(caller_user_id)
    resp['flagStatus'] = flag_manager.enums.FlagStatus.FLAGGED
    return resp


@routes.register('Mutation.archivePost')
def archive_post(caller_user_id, arguments, source, context):
    post_id = arguments['postId']

    post = post_manager.get_post(post_id)
    if not post:
        raise ClientException(f'Post `{post_id}` does not exist')

    if caller_user_id != post.user_id:
        raise ClientException("Cannot archive another User's post")

    try:
        post.archive()
    except post_manager.exceptions.PostException as err:
        raise ClientException(str(err))

    return post.serialize(caller_user_id)


@routes.register('Mutation.deletePost')
def delete_post(caller_user_id, arguments, source, context):
    post_id = arguments['postId']

    post = post_manager.get_post(post_id)
    if not post:
        raise ClientException(f'Post `{post_id}` does not exist')

    if caller_user_id != post.user_id:
        raise ClientException("Cannot delete another User's post")

    try:
        post = post.delete()
    except post_manager.exceptions.PostException as err:
        raise ClientException(str(err))

    return post.serialize(caller_user_id)


@routes.register('Mutation.restoreArchivedPost')
def restore_archived_post(caller_user_id, arguments, source, context):
    post_id = arguments['postId']

    post = post_manager.get_post(post_id)
    if not post:
        raise ClientException(f'Post `{post_id}` does not exist')

    if caller_user_id != post.user_id:
        raise ClientException("Cannot restore another User's post")

    try:
        post.restore()
    except post_manager.exceptions.PostException as err:
        raise ClientException(str(err))

    return post.serialize(caller_user_id)


@routes.register('Mutation.onymouslyLikePost')
def onymously_like_post(caller_user_id, arguments, source, context):
    post_id = arguments['postId']

    post = post_manager.get_post(post_id)
    if not post:
        raise ClientException(f'Post `{post_id}` does not exist')

    user = user_manager.get_user(caller_user_id)
    try:
        like_manager.like_post(user, post, LikeStatus.ONYMOUSLY_LIKED)
    except like_manager.exceptions.LikeException as err:
        raise ClientException(str(err))

    resp = post.serialize(caller_user_id)
    resp['likeStatus'] = LikeStatus.ONYMOUSLY_LIKED
    return resp


@routes.register('Mutation.anonymouslyLikePost')
def anonymously_like_post(caller_user_id, arguments, source, context):
    post_id = arguments['postId']

    post = post_manager.get_post(post_id)
    if not post:
        raise ClientException(f'Post `{post_id}` does not exist')

    user = user_manager.get_user(caller_user_id)
    try:
        like_manager.like_post(user, post, LikeStatus.ANONYMOUSLY_LIKED)
    except like_manager.exceptions.LikeException as err:
        raise ClientException(str(err))

    resp = post.serialize(caller_user_id)
    resp['likeStatus'] = LikeStatus.ANONYMOUSLY_LIKED
    return resp


@routes.register('Mutation.dislikePost')
def dislike_post(caller_user_id, arguments, source, context):
    post_id = arguments['postId']

    post = post_manager.dynamo.get_post(post_id)
    if not post:
        raise ClientException(f'Post `{post_id}` does not exist')

    like = like_manager.get_like(caller_user_id, post_id)
    if not like:
        raise ClientException(f'User has not liked post `{post_id}`, thus cannot dislike it')

    prev_like_status = like.item['likeStatus']
    like.dislike()

    resp = post_manager.init_post(post).serialize(caller_user_id)
    post_like_count = 'onymousLikeCount' if prev_like_status == LikeStatus.ONYMOUSLY_LIKED else 'anonymousLikeCount'
    resp[post_like_count] -= 1
    resp['likeStatus'] = LikeStatus.NOT_LIKED
    return resp


@routes.register('Mutation.reportPostViews')
def report_post_views(caller_user_id, arguments, source, context):
    post_ids = arguments['postIds']
    if len(post_ids) == 0:
        raise ClientException('A minimum of 1 post id must be reported')
    if len(post_ids) > 100:
        raise ClientException('A max of 100 post ids may be reported at a time')

    view_manager.record_views('post', post_ids, caller_user_id)
    return True


@routes.register('Mutation.addComment')
def add_comment(caller_user_id, arguments, source, context):
    comment_id = arguments['commentId']
    post_id = arguments['postId']
    text = arguments['text']

    try:
        comment = comment_manager.add_comment(comment_id, post_id, caller_user_id, text)
    except comment_manager.exceptions.CommentException as err:
        raise ClientException(str(err))

    return comment.serialize(caller_user_id)


@routes.register('Mutation.deleteComment')
def delete_comment(caller_user_id, arguments, source, context):
    comment_id = arguments['commentId']

    comment = comment_manager.get_comment(comment_id)
    if not comment:
        raise ClientException(f'No comment with id `{comment_id}` found')

    try:
        comment.delete(caller_user_id)
    except comment_manager.exceptions.CommentException as err:
        raise ClientException(str(err))

    return comment.serialize(caller_user_id)


@routes.register('Mutation.reportCommentViews')
def report_comment_views(caller_user_id, arguments, source, context):
    comment_ids = arguments['commentIds']
    if len(comment_ids) == 0:
        raise ClientException('A minimum of 1 comment id must be reported')
    if len(comment_ids) > 100:
        raise ClientException('A max of 100 comment ids may be reported at a time')

    view_manager.record_views('comment', comment_ids, caller_user_id)
    return True


@routes.register('Mutation.addAlbum')
def add_album(caller_user_id, arguments, source, context):
    album_id = arguments['albumId']
    name = arguments['name']
    description = arguments.get('description')

    try:
        album = album_manager.add_album(caller_user_id, album_id, name, description=description)
    except album_manager.exceptions.AlbumException as err:
        raise ClientException(str(err))

    return album.serialize(caller_user_id)


@routes.register('Mutation.editAlbum')
def edit_album(caller_user_id, arguments, source, context):
    album_id = arguments['albumId']
    name = arguments.get('name')
    description = arguments.get('description')

    album = album_manager.get_album(album_id)
    if not album:
        raise ClientException(f'Album `{album_id}` does not exist')

    if album.user_id != caller_user_id:
        raise ClientException(f'Caller `{caller_user_id}` does not own Album `{album_id}`')

    try:
        album.update(name=name, description=description)
    except album_manager.exceptions.AlbumException as err:
        raise ClientException(str(err))

    return album.serialize(caller_user_id)


@routes.register('Mutation.deleteAlbum')
def delete_album(caller_user_id, arguments, source, context):
    album_id = arguments['albumId']

    album = album_manager.get_album(album_id)
    if not album:
        raise ClientException(f'Album `{album_id}` does not exist')

    if album.user_id != caller_user_id:
        raise ClientException(f'Caller `{caller_user_id}` does not own Album `{album_id}`')

    try:
        album.delete()
    except album_manager.exceptions.AlbumException as err:
        raise ClientException(str(err))

    return album.serialize(caller_user_id)


@routes.register('Album.art')
def album_art(caller_user_id, arguments, source, context):
    album = album_manager.init_album(source)
    return {
        'url': album.get_art_image_url(image_size.NATIVE),
        'url64p': album.get_art_image_url(image_size.P64),
        'url480p': album.get_art_image_url(image_size.P480),
        'url1080p': album.get_art_image_url(image_size.P1080),
        'url4k': album.get_art_image_url(image_size.K4),
    }


@routes.register('Mutation.createDirectChat')
def create_direct_chat(caller_user_id, arguments, source, context):
    chat_id, user_id = arguments['chatId'], arguments['userId']
    message_id, message_text = arguments['messageId'], arguments['messageText']

    user = user_manager.get_user(user_id)
    if not user:
        raise ClientException(f'User `{user_id}` does not exist')

    now = pendulum.now('utc')
    try:
        chat = chat_manager.add_direct_chat(chat_id, caller_user_id, user_id, now=now)
        message = chat_message_manager.add_chat_message(message_id, message_text, chat_id, caller_user_id, now=now)
    except chat_manager.exceptions.ChatException as err:
        raise ClientException(str(err))

    message.trigger_notifications(message.enums.ChatMessageNotificationType.ADDED, user_ids=[user_id])
    chat.refresh_item(strongly_consistent=True)
    return chat.item


@routes.register('Mutation.createGroupChat')
def create_group_chat(caller_user_id, arguments, source, context):
    chat_id, user_ids, name = arguments['chatId'], arguments['userIds'], arguments.get('name')
    message_id, message_text = arguments['messageId'], arguments['messageText']

    try:
        chat = chat_manager.add_group_chat(chat_id, caller_user_id, name=name)
        chat.add(caller_user_id, user_ids)
        message = chat_message_manager.add_chat_message(message_id, message_text, chat_id, caller_user_id)
    except chat_manager.exceptions.ChatException as err:
        raise ClientException(str(err))

    message.trigger_notifications(message.enums.ChatMessageNotificationType.ADDED, user_ids=user_ids)
    chat.refresh_item(strongly_consistent=True)
    return chat.item


@routes.register('Mutation.editGroupChat')
def edit_group_chat(caller_user_id, arguments, source, context):
    chat_id = arguments['chatId']
    name = arguments.get('name')

    chat = chat_manager.get_chat(chat_id)
    if not chat or not chat.is_member(caller_user_id):
        raise ClientException(f'User `{caller_user_id}` is not a member of chat `{chat_id}`')

    try:
        chat.edit(caller_user_id, name=name)
    except chat_manager.exceptions.ChatException as err:
        raise ClientException(str(err))

    return chat.item


@routes.register('Mutation.addToGroupChat')
def add_to_group_chat(caller_user_id, arguments, source, context):
    chat_id, user_ids = arguments['chatId'], arguments['userIds']

    chat = chat_manager.get_chat(chat_id)
    if not chat or not chat.is_member(caller_user_id):
        raise ClientException(f'User `{caller_user_id}` is not a member of chat `{chat_id}`')

    try:
        chat.add(caller_user_id, user_ids)
    except chat_manager.exceptions.ChatException as err:
        raise ClientException(str(err))

    return chat.item


@routes.register('Mutation.leaveGroupChat')
def leave_group_chat(caller_user_id, arguments, source, context):
    chat_id = arguments['chatId']

    chat = chat_manager.get_chat(chat_id)
    if not chat or not chat.is_member(caller_user_id):
        raise ClientException(f'User `{caller_user_id}` is not a member of chat `{chat_id}`')

    try:
        chat.leave(caller_user_id)
    except chat_manager.exceptions.ChatException as err:
        raise ClientException(str(err))

    return chat.item


@routes.register('Mutation.addChatMessage')
def add_chat_message(caller_user_id, arguments, source, context):
    chat_id, message_id, text = arguments['chatId'], arguments['messageId'], arguments['text']

    chat = chat_manager.get_chat(chat_id)
    if not chat or not chat.is_member(caller_user_id):
        raise ClientException(f'User `{caller_user_id}` is not a member of chat `{chat_id}`')

    try:
        message = chat_message_manager.add_chat_message(message_id, text, chat_id, caller_user_id)
    except chat_manager.exceptions.ChatException as err:
        raise ClientException(str(err))

    message.trigger_notifications(message.enums.ChatMessageNotificationType.ADDED)
    return message.serialize(caller_user_id)


@routes.register('Mutation.editChatMessage')
def edit_chat_message(caller_user_id, arguments, source, context):
    message_id, text = arguments['messageId'], arguments['text']

    message = chat_message_manager.get_chat_message(message_id)
    if not message or message.user_id != caller_user_id:
        raise ClientException(f'User `{caller_user_id}` cannot edit message `{message_id}`')

    try:
        message.edit(text)
    except chat_manager.exceptions.ChatException as err:
        raise ClientException(str(err))

    message.trigger_notifications(message.enums.ChatMessageNotificationType.EDITED)
    return message.serialize(caller_user_id)


@routes.register('Mutation.deleteChatMessage')
def delete_chat_message(caller_user_id, arguments, source, context):
    message_id = arguments['messageId']

    message = chat_message_manager.get_chat_message(message_id)
    if not message or message.user_id != caller_user_id:
        raise ClientException(f'User `{caller_user_id}` cannot delete message `{message_id}`')

    try:
        message.delete()
    except chat_manager.exceptions.ChatException as err:
        raise ClientException(str(err))

    message.trigger_notifications(message.enums.ChatMessageNotificationType.DELETED)
    return message.serialize(caller_user_id)


@routes.register('Mutation.reportChatMessageViews')
def report_chat_message_views(caller_user_id, arguments, source, context):
    message_ids = arguments['messageIds']
    if len(message_ids) == 0:
        raise ClientException('A minimum of 1 message id must be reported')
    if len(message_ids) > 100:
        raise ClientException('A max of 100 message ids may be reported at a time')

    view_manager.record_views('chat_message', message_ids, caller_user_id)
    return True


@routes.register('Mutation.lambdaClientError')
def lambda_client_error(caller_user_id, arguments, source, context):
    request_id = getattr(context, 'aws_request_id', None)
    raise ClientException(f'Test of lambda client error, request `{request_id}`')


@routes.register('Mutation.lambdaServerError')
def lambda_server_error(caller_user_id, arguments, source, context):
    request_id = getattr(context, 'aws_request_id', None)
    raise Exception(f'Test of lambda server error, request `{request_id}`')
