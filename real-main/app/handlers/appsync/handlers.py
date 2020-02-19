import logging
import os

import pendulum

from app.clients import (CloudFrontClient, CognitoClient, DynamoClient, FacebookClient, GoogleClient,
                         SecretsManagerClient, S3Client)
from app.models.album import AlbumManager
from app.models.block import BlockManager
from app.models.comment import CommentManager
from app.models.flag import FlagManager
from app.models.follow import FollowManager
from app.models.follow.enums import FollowStatus
from app.models.followed_first_story import FollowedFirstStoryManager
from app.models.like import LikeManager
from app.models.like.enums import LikeStatus
from app.models.media import MediaManager
from app.models.post import PostManager
from app.models.post_view import PostViewManager
from app.models.user import UserManager

from . import routes
from .exceptions import ClientException

UPLOADS_BUCKET = os.environ.get('UPLOADS_BUCKET')
PLACEHOLDER_PHOTOS_BUCKET = os.environ.get('PLACEHOLDER_PHOTOS_BUCKET')

logger = logging.getLogger()

secrets_manager_client = SecretsManagerClient()
clients = {
    'cloudfront': CloudFrontClient(secrets_manager_client.get_cloudfront_key_pair),
    'cognito': CognitoClient(),
    'dynamo': DynamoClient(),
    'facebook': FacebookClient(),
    'google': GoogleClient(),
    's3_uploads': S3Client(UPLOADS_BUCKET),
    's3_placeholder_photos': S3Client(PLACEHOLDER_PHOTOS_BUCKET),
    'secrets_manager': secrets_manager_client,
}

# shared hash of all managers, allows inter-manager communication
managers = {}
album_manager = managers.get('album') or AlbumManager(clients, managers=managers)
block_manager = managers.get('block') or BlockManager(clients, managers=managers)
comment_manager = managers.get('comment') or CommentManager(clients, managers=managers)
ffs_manager = managers.get('followed_first_story') or FollowedFirstStoryManager(clients, managers=managers)
flag_manager = managers.get('flag') or FlagManager(clients, managers=managers)
follow_manager = managers.get('follow') or FollowManager(clients, managers=managers)
like_manager = managers.get('like') or LikeManager(clients, managers=managers)
media_manager = managers.get('media') or MediaManager(clients, managers=managers)
post_manager = managers.get('post') or PostManager(clients, managers=managers)
post_view_manager = managers.get('post_view') or PostViewManager(clients, managers=managers)
user_manager = managers.get('user') or UserManager(clients, managers=managers)


@routes.register('Mutation.createCognitoOnlyUser')
def create_cognito_only_user(caller_user_id, arguments, source, context):
    username = arguments['username']
    full_name = arguments.get('fullName')
    try:
        user = user_manager.create_cognito_only_user(caller_user_id, username, full_name=full_name)
    except user_manager.exceptions.UserValidationException as err:
        raise ClientException(str(err))
    return user.serialize(caller_user_id)


@routes.register('Mutation.createFacebookUser')
def create_facebook_user(caller_user_id, arguments, source, context):
    username = arguments['username']
    full_name = arguments.get('fullName')
    facebook_access_token = arguments['facebookAccessToken']
    try:
        user = user_manager.create_facebook_user(caller_user_id, username, facebook_access_token, full_name=full_name)
    except user_manager.exceptions.UserValidationException as err:
        raise ClientException(str(err))
    return user.serialize(caller_user_id)


@routes.register('Mutation.createGoogleUser')
def create_google_user(caller_user_id, arguments, source, context):
    username = arguments['username']
    full_name = arguments.get('fullName')
    google_id_token = arguments['googleIdToken']
    try:
        user = user_manager.create_google_user(caller_user_id, username, google_id_token, full_name=full_name)
    except user_manager.exceptions.UserValidationException as err:
        raise ClientException(str(err))
    return user.serialize(caller_user_id)


@routes.register('Mutation.startChangeUserEmail')
def start_change_user_email(caller_user_id, arguments, source, context):
    email = arguments['email']
    user = user_manager.get_user(caller_user_id)
    try:
        user.start_change_contact_attribute('email', email)
    except user_manager.exceptions.UserVerificationException as err:
        raise ClientException(str(err))
    return user.serialize(caller_user_id)


@routes.register('Mutation.finishChangeUserEmail')
def finish_change_user_email(caller_user_id, arguments, source, context):
    access_token = arguments['cognitoAccessToken']
    code = arguments['verificationCode']
    user = user_manager.get_user(caller_user_id)
    try:
        user.finish_change_contact_attribute('email', access_token, code)
    except user_manager.exceptions.UserVerificationException as err:
        raise ClientException(str(err))
    return user.serialize(caller_user_id)


@routes.register('Mutation.startChangeUserPhoneNumber')
def start_change_user_phone_number(caller_user_id, arguments, source, context):
    phone = arguments['phoneNumber']
    user = user_manager.get_user(caller_user_id)
    try:
        user.start_change_contact_attribute('phone', phone)
    except user_manager.exceptions.UserVerificationException as err:
        raise ClientException(str(err))
    return user.serialize(caller_user_id)


@routes.register('Mutation.finishChangeUserPhoneNumber')
def finish_change_user_phone_number(caller_user_id, arguments, source, context):
    access_token = arguments['cognitoAccessToken']
    code = arguments['verificationCode']
    user = user_manager.get_user(caller_user_id)
    try:
        user.finish_change_contact_attribute('phone', access_token, code)
    except user_manager.exceptions.UserVerificationException as err:
        raise ClientException(str(err))
    return user.serialize(caller_user_id)


@routes.register('Mutation.setUserDetails')
def set_user_details(caller_user_id, arguments, source, context):
    username = arguments.get('username')
    full_name = arguments.get('fullName')
    bio = arguments.get('bio')
    photo_media_id = arguments.get('photoMediaId')
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
        username, full_name, bio, photo_media_id, privacy_status, follow_counts_hidden, view_counts_hidden,
        language_code, theme_code, comments_disabled, likes_disabled, sharing_disabled, verification_hidden,
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
        except user_manager.exceptions.UserValidationException as err:
            raise ClientException(str(err))

    # are we setting a new profile picture?
    if photo_media_id is not None:
        if photo_media_id == '':
            media = None
        else:
            media = media_manager.get_media(photo_media_id)
            if not media:
                raise ClientException(f'No media with media_id `{photo_media_id}` found')

            uploaded_status = media_manager.enums.MediaStatus.UPLOADED
            if media.item['mediaStatus'] != uploaded_status:
                raise ClientException(f'Cannot set profile photo to media not in {uploaded_status} status')

        user.update_photo(media)

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

    # for REQUESTED and DENIED, just delete them
    # for FOLLOWING, unfollow so that the other user's counts remain correct
    follow_manager.reset_followed_items(caller_user_id)
    follow_manager.reset_follower_items(caller_user_id)

    # unflag everything we've flagged
    flag_manager.unflag_all_by_user(caller_user_id)

    # delete all our posts, and all likes on those posts
    for post_item in post_manager.dynamo.generate_posts_by_user(caller_user_id):
        post_manager.init_post(post_item).delete()

    # delete all our likes & comments & albums
    like_manager.dislike_all_by_user(caller_user_id)
    comment_manager.delete_all_by_user(caller_user_id)
    album_manager.delete_all_by_user(caller_user_id)

    # remove all blocks of and by us
    block_manager.unblock_all_blocks(caller_user_id)

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
    except user_manager.exceptions.UserValidationException as err:
        raise ClientException(str(err))
    return user.serialize(caller_user_id)


@routes.register('User.photoUrl')
def user_photo_url(caller_user_id, arguments, source, context):
    user = user_manager.init_user(source)
    return user.get_photo_url(media_manager.enums.MediaSize.NATIVE)


@routes.register('User.photoUrl64p')
def user_photo_url_64p(caller_user_id, arguments, source, context):
    user = user_manager.init_user(source)
    return user.get_photo_url(media_manager.enums.MediaSize.P64)


@routes.register('User.photoUrl480p')
def user_photo_url_480p(caller_user_id, arguments, source, context):
    user = user_manager.init_user(source)
    return user.get_photo_url(media_manager.enums.MediaSize.P480)


@routes.register('User.photoUrl1080p')
def user_photo_url_1080p(caller_user_id, arguments, source, context):
    user = user_manager.init_user(source)
    return user.get_photo_url(media_manager.enums.MediaSize.P1080)


@routes.register('User.photoUrl4k')
def user_photo_url_4k(caller_user_id, arguments, source, context):
    user = user_manager.init_user(source)
    return user.get_photo_url(media_manager.enums.MediaSize.K4)


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

    # can't follow a user that has blocked us
    if block_manager.is_blocked(followed_user_id, follower_user_id):
        raise ClientException(f'User has been blocked by user `{followed_user_id}`')

    # can't follow a user we have blocked
    if block_manager.is_blocked(follower_user_id, followed_user_id):
        raise ClientException(f'User has blocked user `{followed_user_id}`')

    try:
        follow_status = follow_manager.request_to_follow(follower_user, followed_user)
    except follow_manager.exceptions.FollowException as err:
        raise ClientException(str(err))

    resp = followed_user.serialize(caller_user_id)
    resp['followedStatus'] = follow_status
    if follow_status == FollowStatus.FOLLOWING:
        resp['followerCount'] = followed_user.item.get('followerCount', 0) + 1
    return resp


@routes.register('Mutation.unfollowUser')
def unfollow_user(caller_user_id, arguments, source, context):
    follower_user_id = caller_user_id
    followed_user_id = arguments['userId']

    try:
        follow_manager.unfollow(follower_user_id, followed_user_id)
    except follow_manager.exceptions.FollowException as err:
        raise ClientException(str(err))

    resp = user_manager.get_user(followed_user_id).serialize(caller_user_id)
    resp['followedStatus'] = FollowStatus.NOT_FOLLOWING
    # TODO: decrement followerCount if needed
    return resp


@routes.register('Mutation.acceptFollowerUser')
def accept_follower_user(caller_user_id, arguments, source, context):
    user_id = arguments['userId']

    try:
        follow_manager.accept_follow_request(user_id, caller_user_id)
    except follow_manager.exceptions.FollowException as err:
        raise ClientException(str(err))

    resp = user_manager.get_user(user_id).serialize(caller_user_id)
    resp['followerStatus'] = FollowStatus.FOLLOWING
    # TODO: increment followerCount if needed
    return resp


@routes.register('Mutation.denyFollowerUser')
def deny_follower_user(caller_user_id, arguments, source, context):
    user_id = arguments['userId']

    try:
        follow_manager.deny_follow_request(user_id, caller_user_id)
    except follow_manager.exceptions.FollowException as err:
        raise ClientException(str(err))

    resp = user_manager.get_user(user_id).serialize(caller_user_id)
    resp['followerStatus'] = FollowStatus.DENIED
    # TODO: decrement followerCount if needed
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
        block_item = block_manager.block(blocker_user, blocked_user)
    except block_manager.exceptions.AlreadyBlocked as err:
        raise ClientException(str(err))

    resp = blocked_user.serialize(caller_user_id)
    resp['blockedAt'] = block_item['blockedAt']
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
    resp['blockedAt'] = None
    resp['blockedStatus'] = block_manager.enums.BlockStatus.NOT_BLOCKING
    return resp


@routes.register('Mutation.addPost')
def add_post(caller_user_id, arguments, source, context):
    user = user_manager.get_user(caller_user_id)
    if not user:
        raise ClientException(f'User `{caller_user_id}` does not exist')

    post_id = arguments['postId']
    text = arguments.get('text')
    media = arguments.get('mediaObjectUploads', [])
    album_id = arguments.get('albumId')

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
            user.id, post_id, media_uploads=media, text=text, lifetime_duration=lifetime_duration, album_id=album_id,
            comments_disabled=comments_disabled, likes_disabled=likes_disabled, sharing_disabled=sharing_disabled,
            verification_hidden=verification_hidden,
        )
    except post_manager.exceptions.PostException as err:
        raise ClientException(str(err))

    resp = post.serialize(caller_user_id)

    # if the posts was completed right away (ie a text-only post), then the user's postCount was incremented
    if post.post_status == post_manager.enums.PostStatus.COMPLETED:
        resp['postedBy']['postCount'] = org_post_count + 1

    return resp


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

    if caller_user_id != post.item['postedByUserId']:
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

    if caller_user_id != post.item['postedByUserId']:
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

    if caller_user_id != post.item['postedByUserId']:
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
    expires_at = pendulum.parse(expires_at_str).in_tz('utc') if expires_at_str else None

    post = post_manager.get_post(post_id)
    if not post:
        raise ClientException(f'Post `{post_id}` does not exist')

    if caller_user_id != post.item['postedByUserId']:
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

    if caller_user_id != post.item['postedByUserId']:
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

    if caller_user_id != post.item['postedByUserId']:
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

    if caller_user_id != post.item['postedByUserId']:
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


@routes.register('MediaObject.url')
def media_objects_url(caller_user_id, arguments, source, context):
    return media_manager.init_media(source).get_readonly_url(media_manager.enums.MediaSize.NATIVE)


@routes.register('MediaObject.url64p')
def media_objects_url_64p(caller_user_id, arguments, source, context):
    return media_manager.init_media(source).get_readonly_url(media_manager.enums.MediaSize.P64)


@routes.register('MediaObject.url480p')
def media_objects_url_480p(caller_user_id, arguments, source, context):
    return media_manager.init_media(source).get_readonly_url(media_manager.enums.MediaSize.P480)


@routes.register('MediaObject.url1080p')
def media_objects_url_1080p(caller_user_id, arguments, source, context):
    return media_manager.init_media(source).get_readonly_url(media_manager.enums.MediaSize.P1080)


@routes.register('MediaObject.url4k')
def media_objects_url_4k(caller_user_id, arguments, source, context):
    return media_manager.init_media(source).get_readonly_url(media_manager.enums.MediaSize.K4)


@routes.register('MediaObject.uploadUrl')
def media_objects_upload_url(caller_user_id, arguments, source, context):
    # only the owner of the post gets an upload url
    if caller_user_id != source['userId']:
        return None
    return media_manager.init_media(source).get_writeonly_url()


@routes.register('Mutation.reportPostViews')
def report_post_views(caller_user_id, arguments, source, context):
    post_ids = arguments['postIds']
    if len(post_ids) == 0:
        raise ClientException('A minimum of 1 post id must be reported')
    if len(post_ids) > 100:
        raise ClientException('A max of 100 post ids may be reported at a time')

    post_view_manager.record_views(caller_user_id, post_ids)
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

    try:
        comment = comment_manager.delete_comment(comment_id, caller_user_id)
    except comment_manager.exceptions.CommentException as err:
        raise ClientException(str(err))

    return comment.serialize(caller_user_id)


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

    if album.item['ownedByUserId'] != caller_user_id:
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

    if album.item['ownedByUserId'] != caller_user_id:
        raise ClientException(f'Caller `{caller_user_id}` does not own Album `{album_id}`')

    try:
        album.delete()
    except album_manager.exceptions.AlbumException as err:
        raise ClientException(str(err))

    return album.serialize(caller_user_id)


@routes.register('Album.url')
def album_url(caller_user_id, arguments, source, context):
    album = album_manager.init_album(source)
    return album.get_art_image_url(media_manager.enums.MediaSize.NATIVE)


@routes.register('Album.url64p')
def album_url_64p(caller_user_id, arguments, source, context):
    album = album_manager.init_album(source)
    return album.get_art_image_url(media_manager.enums.MediaSize.P64)


@routes.register('Album.url480p')
def album_url_480p(caller_user_id, arguments, source, context):
    album = album_manager.init_album(source)
    return album.get_art_image_url(media_manager.enums.MediaSize.P480)


@routes.register('Album.url1080p')
def album_url_1080p(caller_user_id, arguments, source, context):
    album = album_manager.init_album(source)
    return album.get_art_image_url(media_manager.enums.MediaSize.P1080)


@routes.register('Album.url4k')
def album_url_4k(caller_user_id, arguments, source, context):
    album = album_manager.init_album(source)
    return album.get_art_image_url(media_manager.enums.MediaSize.K4)


@routes.register('Mutation.lambdaClientError')
def lambda_client_error(caller_user_id, arguments, source, context):
    request_id = getattr(context, 'aws_request_id', None)
    raise ClientException(f'Test of lambda client error, request `{request_id}`')


@routes.register('Mutation.lambdaServerError')
def lambda_server_error(caller_user_id, arguments, source, context):
    request_id = getattr(context, 'aws_request_id', None)
    raise Exception(f'Test of lambda server error, request `{request_id}`')
