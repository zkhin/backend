import collections
import itertools
import logging

import pendulum

from app import models
from app.mixins.base import ManagerBase
from app.mixins.flag.manager import FlagManagerMixin
from app.mixins.trending.manager import TrendingManagerMixin
from app.mixins.view.manager import ViewManagerMixin

from .appsync import PostAppSync
from .dynamo import PostDynamo, PostImageDynamo, PostOriginalMetadataDynamo
from .enums import PostType
from .exceptions import PostException
from .model import Post
from .postprocessor import PostPostProcessor

logger = logging.getLogger()


class PostManager(FlagManagerMixin, TrendingManagerMixin, ViewManagerMixin, ManagerBase):

    item_type = 'post'

    def __init__(self, clients, managers=None):
        super().__init__(clients, managers=managers)
        managers = managers or {}
        managers['post'] = self
        self.album_manager = managers.get('album') or models.AlbumManager(clients, managers=managers)
        self.block_manager = managers.get('block') or models.BlockManager(clients, managers=managers)
        self.card_manager = managers.get('card') or models.CardManager(clients, managers=managers)
        self.comment_manager = managers.get('comment') or models.CommentManager(clients, managers=managers)
        self.feed_manager = managers.get('feed') or models.FeedManager(clients, managers=managers)
        self.follower_manager = managers.get('follower') or models.FollowerManager(clients, managers=managers)
        self.like_manager = managers.get('like') or models.LikeManager(clients, managers=managers)
        self.user_manager = managers.get('user') or models.UserManager(clients, managers=managers)

        self.clients = clients
        if 'appsync' in clients:
            self.appsync = PostAppSync(clients['appsync'])
        if 'dynamo' in clients:
            self.dynamo = PostDynamo(clients['dynamo'])
            self.image_dynamo = PostImageDynamo(clients['dynamo'])
            self.original_metadata_dynamo = PostOriginalMetadataDynamo(clients['dynamo'])

    @property
    def postprocessor(self):
        if not hasattr(self, '_postprocessor'):
            self._postprocessor = PostPostProcessor(
                dynamo=getattr(self, 'dynamo', None),
                view_dynamo=getattr(self, 'view_dynamo', None),
                manager=self,
                comment_manager=self.comment_manager,
            )
        return self._postprocessor

    def get_model(self, item_id, strongly_consistent=False):
        return self.get_post(item_id, strongly_consistent=strongly_consistent)

    def get_post(self, post_id, strongly_consistent=False):
        post_item = self.dynamo.get_post(post_id, strongly_consistent=strongly_consistent)
        return self.init_post(post_item) if post_item else None

    def init_post(self, post_item):
        kwargs = {
            'post_appsync': getattr(self, 'appsync', None),
            'post_dynamo': getattr(self, 'dynamo', None),
            'post_image_dynamo': getattr(self, 'image_dynamo', None),
            'post_original_metadata_dynamo': getattr(self, 'original_metadata_dynamo', None),
            'flag_dynamo': getattr(self, 'flag_dynamo', None),
            'trending_dynamo': getattr(self, 'trending_dynamo', None),
            'view_dynamo': getattr(self, 'view_dynamo', None),
            'cloudfront_client': self.clients.get('cloudfront'),
            'mediaconvert_client': self.clients.get('mediaconvert'),
            'post_verification_client': self.clients.get('post_verification'),
            's3_uploads_client': self.clients.get('s3_uploads'),
            'album_manager': self.album_manager,
            'block_manager': self.block_manager,
            'card_manager': self.card_manager,
            'comment_manager': self.comment_manager,
            'feed_manager': self.feed_manager,
            'follower_manager': self.follower_manager,
            'like_manager': self.like_manager,
            'post_manager': self,
            'user_manager': self.user_manager,
        }
        return Post(post_item, **kwargs) if post_item else None

    def add_post(
        self,
        posted_by_user,
        post_id,
        post_type,
        image_input=None,
        text=None,
        lifetime_duration=None,
        album_id=None,
        comments_disabled=None,
        likes_disabled=None,
        sharing_disabled=None,
        verification_hidden=None,
        set_as_user_photo=None,
        now=None,
    ):
        now = now or pendulum.now('utc')
        text = None if text == '' else text  # treat empty string as equivalent of null

        if post_type == PostType.TEXT_ONLY:
            if not text:
                raise PostException('Cannot add text-only post without text')
            if image_input:
                raise PostException('Cannot add text-only post with ImageInput')
            if set_as_user_photo:
                raise PostException('Cannot add text-only post with setAsUserPhoto')

        elif post_type == PostType.VIDEO:
            if image_input:
                raise PostException('Cannot add video post with ImageInput')
            if set_as_user_photo:
                raise PostException('Cannot add video post with setAsUserPhoto')

        elif post_type == PostType.IMAGE:
            if image_input and (crop := image_input.get('crop')):
                for pt, coord in itertools.product(('upperLeft', 'lowerRight'), ('x', 'y')):
                    if crop[pt][coord] < 0:
                        raise PostException(f'Image crop {pt}.{coord} cannot be negative')
                for coord in ('x', 'y'):
                    if crop['upperLeft'][coord] >= crop['lowerRight'][coord]:
                        raise PostException(
                            f'Image crop lowerRight.{coord} must be strictly greater than upperLeft.{coord}',
                        )
        else:
            raise Exception(f'Invalid PostType `{post_type}`')

        expires_at = now + lifetime_duration if lifetime_duration is not None else None
        if expires_at and expires_at <= now:
            msg = f'Refusing to add post `{post_id}` for user `{posted_by_user.id}` with non-positive lifetime'
            raise PostException(msg)

        text_tags = self.user_manager.get_text_tags(text) if text is not None else None

        # pull in user-level defaults for settings as needed
        if comments_disabled is None:
            comments_disabled = posted_by_user.item.get('commentsDisabled')
        if likes_disabled is None:
            likes_disabled = posted_by_user.item.get('likesDisabled')
        if sharing_disabled is None:
            sharing_disabled = posted_by_user.item.get('sharingDisabled')
        if verification_hidden is None:
            verification_hidden = posted_by_user.item.get('verificationHidden')

        # if an album is specified, verify it exists and is ours
        if album_id:
            album = self.album_manager.get_album(album_id)
            if not album:
                raise PostException(f'Album `{album_id}` does not exist')
            if album.user_id != posted_by_user.id:
                msg = f'Album `{album_id}` does not belong to caller user `{posted_by_user.id}`'
                raise PostException(msg)

        # add the pending post & media to dynamo in a transaction
        transacts = [
            self.dynamo.transact_add_pending_post(
                posted_by_user.id,
                post_id,
                post_type,
                posted_at=now,
                expires_at=expires_at,
                text=text,
                text_tags=text_tags,
                comments_disabled=comments_disabled,
                likes_disabled=likes_disabled,
                sharing_disabled=sharing_disabled,
                verification_hidden=verification_hidden,
                album_id=album_id,
                set_as_user_photo=set_as_user_photo,
            )
        ]
        if post_type == PostType.IMAGE:
            # 'image_input' is straight from graphql, format dictated by schema
            image_input = image_input or {}
            transacts.append(
                self.image_dynamo.transact_add(
                    post_id,
                    crop=image_input.get('crop'),
                    image_format=image_input.get('imageFormat'),
                    original_format=image_input.get('originalFormat'),
                    taken_in_real=image_input.get('takenInReal'),
                )
            )
            if original_metadata := image_input.get('originalMetadata'):
                transacts.append(self.original_metadata_dynamo.transact_add(post_id, original_metadata))
        self.dynamo.client.transact_write_items(transacts)

        post_item = self.dynamo.get_post(post_id, strongly_consistent=True)
        post = self.init_post(post_item)

        # text-only posts can be completed immediately
        if post.type == PostType.TEXT_ONLY:
            post.complete(now=now)

        if post.type == PostType.IMAGE:
            if image_data := image_input.get('imageData'):
                post.refresh_image_item(strongly_consistent=True)
                try:
                    post.process_image_upload(image_data=image_data, now=now)
                except PostException as err:
                    logger.warning(str(err))
                    post.error()

        return post

    def record_views(self, post_ids, user_id, viewed_at=None):
        grouped_post_ids = dict(collections.Counter(post_ids))
        if not grouped_post_ids:
            return

        for post_id, view_count in grouped_post_ids.items():
            post = self.get_post(post_id)
            if not post:
                logger.warning(f'Cannot record view(s) by user `{user_id}` on DNE post `{post_id}`')
                continue
            post.record_view_count(user_id, view_count, viewed_at=viewed_at)

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

    def delete_all_by_user(self, user_id):
        for post_item in self.dynamo.generate_posts_by_user(user_id):
            self.init_post(post_item).delete()

    def on_flag_added(self, post_id, user_id):
        post_item = self.dynamo.increment_flag_count(post_id)
        post = self.init_post(post_item)

        # force archive the post?
        user = self.user_manager.get_user(user_id)
        if user.username in post.flag_admin_usernames or post.is_crowdsourced_forced_removal_criteria_met():
            logger.warning(f'Force archiving post `{post_id}` from flagging')
            post.archive(forced=True)
