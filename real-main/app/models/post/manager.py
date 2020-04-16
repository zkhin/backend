import itertools
import logging
import uuid

import pendulum

from app.models import album, comment, feed, flag, followed_first_story, like, media, trending, user, view
from app.models.media.enums import MediaStatus

from . import enums, exceptions
from .appsync import PostAppSync
from .dynamo import PostDynamo
from .model import Post

logger = logging.getLogger()


class PostManager:

    enums = enums
    exceptions = exceptions

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['post'] = self
        self.album_manager = managers.get('album') or album.AlbumManager(clients, managers=managers)
        self.comment_manager = managers.get('comment') or comment.CommentManager(clients, managers=managers)
        self.feed_manager = managers.get('feed') or feed.FeedManager(clients, managers=managers)
        self.flag_manager = managers.get('flag') or flag.FlagManager(clients, managers=managers)
        self.followed_first_story_manager = (
            managers.get('followed_first_story')
            or followed_first_story.FollowedFirstStoryManager(clients, managers=managers)
        )
        self.like_manager = managers.get('like') or like.LikeManager(clients, managers=managers)
        self.media_manager = managers.get('media') or media.MediaManager(clients, managers=managers)
        self.trending_manager = managers.get('trending') or trending.TrendingManager(clients, managers=managers)
        self.user_manager = managers.get('user') or user.UserManager(clients, managers=managers)
        self.view_manager = managers.get('view') or view.ViewManager(clients, managers=managers)

        self.clients = clients
        if 'appsync' in clients:
            self.appsync = PostAppSync(clients['appsync'])
        if 'dynamo' in clients:
            self.dynamo = PostDynamo(clients['dynamo'])

    def get_post(self, post_id, strongly_consistent=False):
        post_item = self.dynamo.get_post(post_id, strongly_consistent=strongly_consistent)
        return self.init_post(post_item) if post_item else None

    def init_post(self, post_item):
        kwargs = {
            'post_appsync': getattr(self, 'appsync', None),
            'post_dynamo': getattr(self, 'dynamo', None),
            'cloudfront_client': self.clients.get('cloudfront'),
            'mediaconvert_client': self.clients.get('mediaconvert'),
            's3_uploads_client': self.clients.get('s3_uploads'),
            'album_manager': self.album_manager,
            'comment_manager': self.comment_manager,
            'feed_manager': self.feed_manager,
            'flag_manager': self.flag_manager,
            'followed_first_story_manager': self.followed_first_story_manager,
            'like_manager': self.like_manager,
            'media_manager': self.media_manager,
            'post_manager': self,
            'trending_manager': self.trending_manager,
            'user_manager': self.user_manager,
            'view_manager': self.view_manager,
        }
        return Post(post_item, **kwargs) if post_item else None

    def add_post(self, posted_by_user_id, post_id, post_type, image_input=None, text=None, lifetime_duration=None,
                 album_id=None, comments_disabled=None, likes_disabled=None, sharing_disabled=None,
                 verification_hidden=None, now=None):
        now = now or pendulum.now('utc')
        text = None if text == '' else text  # treat empty string as equivalent of null

        image_input = image_input or {}
        if post_type == enums.PostType.IMAGE and 'mediaId' not in image_input:
            image_input['mediaId'] = str(uuid.uuid4())

        if post_type == enums.PostType.TEXT_ONLY:
            if not text:
                raise exceptions.PostException('Cannot add text-only post without text')
            if image_input:
                raise exceptions.PostException('Cannot add text-only post with ImageInput')

        if post_type == enums.PostType.VIDEO and image_input:
            raise exceptions.PostException('Cannot add video post with ImageInput')

        expires_at = now + lifetime_duration if lifetime_duration is not None else None
        if expires_at and expires_at <= now:
            msg = f'Refusing to add post `{post_id}` for user `{posted_by_user_id}` with non-positive lifetime'
            raise exceptions.PostException(msg)

        text_tags = self.user_manager.get_text_tags(text) if text is not None else None

        # if an album is specified, verify it exists and is ours
        if album_id:
            album = self.album_manager.get_album(album_id)
            if not album:
                raise exceptions.PostException(f'Album `{album_id}` does not exist')
            if album.user_id != posted_by_user_id:
                msg = f'Album `{album_id}` does not belong to caller user `{posted_by_user_id}`'
                raise exceptions.PostException(msg)

        # add the pending post & media to dynamo in a transaction
        transacts = [self.dynamo.transact_add_pending_post(
            posted_by_user_id, post_id, post_type, posted_at=now, expires_at=expires_at, text=text,
            text_tags=text_tags, comments_disabled=comments_disabled, likes_disabled=likes_disabled,
            sharing_disabled=sharing_disabled, verification_hidden=verification_hidden, album_id=album_id,
        )]
        if post_type == enums.PostType.IMAGE:
            # 'image_input' is straight from graphql, format dictated by schema
            transacts.append(self.media_manager.dynamo.transact_add_media(
                posted_by_user_id, post_id, image_input['mediaId'], media_status=MediaStatus.AWAITING_UPLOAD,
                posted_at=now, taken_in_real=image_input.get('takenInReal'),
                original_format=image_input.get('originalFormat'),
                image_format=image_input.get('imageFormat'),
            ))
            if original_metadata := image_input.get('originalMetadata'):
                transacts.append(self.dynamo.transact_add_original_metadata(post_id, original_metadata))
        self.dynamo.client.transact_write_items(transacts)

        post_item = self.dynamo.get_post(post_id, strongly_consistent=True)
        post = self.init_post(post_item)

        # text-only posts can be completed immediately
        if post.type == enums.PostType.TEXT_ONLY:
            post.complete(now=now)

        media_items = []
        if post.type == enums.PostType.IMAGE:
            media = self.media_manager.get_media(image_input['mediaId'], strongly_consistent=True)

            # if image data was directly included for any media objects, process it
            if image_data := image_input.get('imageData'):
                post.process_image_upload(image_data=image_data, media=media, now=now)

            media_items.append(media.item)

        post.item['mediaObjects'] = media_items
        return post

    def delete_recently_expired_posts(self, now=None):
        "Delete posts that expired yesterday or today"
        now = now or pendulum.now('utc')
        yesterday = now - pendulum.duration(days=1)

        # Every run we operate on all posts that expired yesterday, and any that have expired so far today.
        # Techinically we only need to operate on yesterday's posts on today's first run,
        # but in the interest of avoiding any 'left behind' posts we do it every time.

        yesterdays_post_pks = self.dynamo.generate_expired_post_pks_by_day(yesterday.date())
        todays_post_pks = self.dynamo.generate_expired_post_pks_by_day(now.date(), now.time())

        # scan for expired posts
        for post_pk in itertools.chain(yesterdays_post_pks, todays_post_pks):
            post_item = self.dynamo.client.get_item(post_pk)
            user_item = self.user_manager.dynamo.get_user(post_item['postedByUserId'])
            logger.warning(
                f'Deleting expired post with pk ({post_pk["partitionKey"]}, {post_pk["sortKey"]}):'
                + f', posted by `{user_item["username"]}`'
                + f', posted at `{post_item.get("postedAt")}`'
                + f', with text `{post_item.get("text")}`'
                + f', with status `{post_item.get("postStatus")}`'
                + f', expired at `{post_item.get("expiresAt")}`'
            )
            self.init_post(post_item).delete()

    def delete_older_expired_posts(self, now=None):
        "Delete posts that expired yesterday or earlier, via full table scan"
        now = now or pendulum.now('utc')
        today = now.date()

        # scan for expired posts
        for post_pk in self.dynamo.generate_expired_post_pks_with_scan(today):  # excludes today
            logger.warning(f'Deleting expired post with pk ({post_pk["partitionKey"]}, {post_pk["sortKey"]})')
            post_item = self.dynamo.client.get_item(post_pk)
            self.init_post(post_item).delete()
