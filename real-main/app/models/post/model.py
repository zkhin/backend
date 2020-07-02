import base64
import io
import logging

import colorthief
import pendulum
import PIL.Image

from app.mixins.flag.model import FlagModelMixin
from app.mixins.trending.model import TrendingModelMixin
from app.mixins.view.model import ViewModelMixin
from app.models.card.specs import CommentCardSpec
from app.models.follower.enums import FollowStatus
from app.models.user.enums import UserPrivacyStatus
from app.models.user.exceptions import UserException
from app.utils import image_size

from .cached_image import CachedImage
from .enums import PostNotificationType, PostStatus, PostType
from .exceptions import PostDoesNotExist, PostException
from .text_image import generate_text_image

logger = logging.getLogger()

# keep in sync with object created handlers defined serverless.yml
VIDEO_ORIGINAL_FILENAME = 'video-original.mov'
VIDEO_HLS_PREFIX = 'video-hls/video'
VIDEO_POSTER_PREFIX = 'video-poster/poster'
IMAGE_DIR = 'image'


class Post(FlagModelMixin, TrendingModelMixin, ViewModelMixin):

    exception_dne = PostDoesNotExist
    exception_generic = PostException
    item_type = 'post'

    def __init__(
        self,
        item,
        post_appsync=None,
        post_dynamo=None,
        post_image_dynamo=None,
        post_original_metadata_dynamo=None,
        cloudfront_client=None,
        mediaconvert_client=None,
        post_verification_client=None,
        s3_uploads_client=None,
        album_manager=None,
        block_manager=None,
        card_manager=None,
        comment_manager=None,
        feed_manager=None,
        followed_first_story_manager=None,
        follower_manager=None,
        like_manager=None,
        post_manager=None,
        user_manager=None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        if post_appsync:
            self.appsync = post_appsync
        if post_dynamo:
            self.dynamo = post_dynamo
        if post_image_dynamo:
            self.image_dynamo = post_image_dynamo
        if post_original_metadata_dynamo:
            self.original_metadata_dynamo = post_original_metadata_dynamo

        if cloudfront_client:
            self.cloudfront_client = cloudfront_client
        if mediaconvert_client:
            self.mediaconvert_client = mediaconvert_client
        if post_verification_client:
            self.post_verification_client = post_verification_client
        if s3_uploads_client:
            self.s3_uploads_client = s3_uploads_client

        if album_manager:
            self.album_manager = album_manager
        if block_manager:
            self.block_manager = block_manager
        if card_manager:
            self.card_manager = card_manager
        if comment_manager:
            self.comment_manager = comment_manager
        if feed_manager:
            self.feed_manager = feed_manager
        if follower_manager:
            self.follower_manager = follower_manager
        if followed_first_story_manager:
            self.followed_first_story_manager = followed_first_story_manager
        if like_manager:
            self.like_manager = like_manager
        if post_manager:
            self.post_manager = post_manager
        if user_manager:
            self.user_manager = user_manager

        self.item = item
        # immutables
        self.id = item['postId']
        self.type = self.item['postType']
        self.user_id = item['postedByUserId']

        # lazy caches
        if self.type == PostType.TEXT_ONLY:

            def upstream_source(dims):
                return generate_text_image(self.item['text'], dims)

            self.k4_jpeg_cache = CachedImage(self.id, image_size.K4, source=upstream_source)
            self.p1080_jpeg_cache = CachedImage(self.id, image_size.P1080, source=upstream_source)
        elif s3_uploads_client:
            self.native_heic_cache = CachedImage(
                self.id,
                image_size.NATIVE_HEIC,
                s3_client=s3_uploads_client,
                s3_path=self.get_image_path(image_size.NATIVE_HEIC),
            )
            self.native_jpeg_cache = CachedImage(
                self.id,
                image_size.NATIVE,
                s3_client=s3_uploads_client,
                s3_path=self.get_image_path(image_size.NATIVE),
            )
            self.k4_jpeg_cache = CachedImage(
                self.id, image_size.K4, s3_client=s3_uploads_client, s3_path=self.get_image_path(image_size.K4)
            )
            self.p1080_jpeg_cache = CachedImage(
                self.id,
                image_size.P1080,
                s3_client=s3_uploads_client,
                s3_path=self.get_image_path(image_size.P1080),
            )
            self.p480_jpeg_cache = CachedImage(
                self.id,
                image_size.P480,
                s3_client=s3_uploads_client,
                s3_path=self.get_image_path(image_size.P480),
            )
            self.p64_jpeg_cache = CachedImage(
                self.id, image_size.P64, s3_client=s3_uploads_client, s3_path=self.get_image_path(image_size.P64)
            )

    @property
    def status(self):
        return self.item['postStatus']

    @property
    def posted_at(self):
        return pendulum.parse(self.item['postedAt'])

    @property
    def s3_prefix(self):
        return '/'.join([self.user_id, 'post', self.id])

    @property
    def image_item(self):
        this = self if hasattr(self, '_image_item') else self.refresh_image_item()
        return this._image_item

    @property
    def user(self):
        if not hasattr(self, '_user'):
            self._user = self.user_manager.get_user(self.user_id)
        return self._user

    @property
    def is_verified(self):
        return self.item.get('isVerified')

    @property
    def original_post_id(self):
        return self.item.get('originalPostId', self.id)

    def refresh_item(self, strongly_consistent=False):
        self.item = self.dynamo.get_post(self.id, strongly_consistent=strongly_consistent)
        return self

    def refresh_image_item(self, strongly_consistent=False):
        self._image_item = self.image_dynamo.get(self.id, strongly_consistent=strongly_consistent)
        return self

    def get_s3_image_path(self, size):
        "From within the user's directory, return the path to the s3 object of the requested size"
        return '/'.join([self.item['postedByUserId'], 'post', self.item['postId'], 'image', size.filename])

    def get_original_video_path(self):
        return f'{self.s3_prefix}/{VIDEO_ORIGINAL_FILENAME}'

    def get_poster_video_path_prefix(self):
        return f'{self.s3_prefix}/{VIDEO_POSTER_PREFIX}'

    def get_poster_path(self):
        return f'{self.s3_prefix}/{VIDEO_POSTER_PREFIX}.0000000.jpg'

    def get_image_path(self, size):
        return f'{self.s3_prefix}/{IMAGE_DIR}/{size.filename}'

    def get_hls_video_path_prefix(self):
        return f'{self.s3_prefix}/{VIDEO_HLS_PREFIX}'

    def get_hls_master_m3u8_url(self):
        path = f'{self.s3_prefix}/{VIDEO_HLS_PREFIX}.m3u8'
        return self.cloudfront_client.generate_unsigned_url(path)

    def get_hls_access_cookies(self):
        s3_path = self.get_hls_video_path_prefix()
        signature_path = s3_path + '*'
        cookie_path = '/' + '/'.join(s3_path.split('/')[:-1]) + '/'  # remove trailing partial filename
        cookies = self.cloudfront_client.generate_presigned_cookies(signature_path)
        return {
            'domain': self.cloudfront_client.domain,
            'path': cookie_path,
            'expiresAt': cookies['ExpiresAt'],
            'policy': cookies['CloudFront-Policy'],
            'signature': cookies['CloudFront-Signature'],
            'keyPairId': cookies['CloudFront-Key-Pair-Id'],
        }

    def get_video_writeonly_url(self):
        path = self.get_original_video_path()
        return self.cloudfront_client.generate_presigned_url(path, ['PUT'])

    def get_image_readonly_url(self, size):
        path = self.get_image_path(size)
        return self.cloudfront_client.generate_presigned_url(path, ['GET', 'HEAD'])

    def get_image_writeonly_url(self):
        assert self.type == PostType.IMAGE
        # protect against this being called before dynamo index has converged
        if not self.image_item:
            return None
        size = image_size.NATIVE_HEIC if self.image_item.get('imageFormat') == 'HEIC' else image_size.NATIVE
        path = self.get_image_path(size)
        return self.cloudfront_client.generate_presigned_url(path, ['PUT'])

    def delete_s3_video(self):
        path = self.get_original_video_path()
        self.s3_uploads_client.delete_object(path)

    def serialize(self, caller_user_id):
        resp = self.item.copy()
        resp['postedBy'] = self.user_manager.get_user(self.user_id).serialize(caller_user_id)
        return resp

    def build_image_thumbnails(self):
        image = self.native_jpeg_cache.get_image()
        # ordered by decreasing size
        for cache in (self.k4_jpeg_cache, self.p1080_jpeg_cache, self.p480_jpeg_cache, self.p64_jpeg_cache):
            fh = io.BytesIO()
            try:
                image.thumbnail(cache.image_size.max_dimensions, resample=PIL.Image.LANCZOS)
                image.save(fh, format='JPEG', quality=100, icc_profile=image.info.get('icc_profile'))
            except Exception as err:
                raise PostException(f'Unable to thumbnail image as jpeg for post `{self.id}`: {err}')
            cache.set(image=image)
            cache.flush()

    def process_image_upload(self, image_data=None, now=None):
        assert self.type == PostType.IMAGE, 'Can only process_image_upload() for IMAGE posts'
        assert self.status in (
            PostStatus.PENDING,
            PostStatus.ERROR,
        ), 'Can only process_image_upload() for PENDING & ERROR posts'
        now = now or pendulum.now('utc')

        # mark ourselves as processing
        transacts = [self.dynamo.transact_set_post_status(self.item, PostStatus.PROCESSING)]
        self.dynamo.client.transact_write_items(transacts)
        self.item['postStatus'] = PostStatus.PROCESSING

        if image_data:
            # s3 trigger is a no-op because we are already in PROCESSING
            self.upload_native_image_data_base64(image_data)

        if self.image_item.get('imageFormat') == 'HEIC':
            self.fill_native_jpeg_cache_from_heic()
        if self.image_item.get('crop'):
            self.crop_native_jpeg_cache()
        if self.native_jpeg_cache.is_synced is False:
            self.native_jpeg_cache.flush()

        if self.image_item.get('imageFormat') == 'HEIC':
            self.native_heic_cache.clear()
            self.native_heic_cache.flush(include_deletes=True)

        self.build_image_thumbnails()
        self.set_height_and_width()
        self.set_colors()
        self.set_is_verified()
        self.set_checksum()
        self.complete(now=now)

    def fill_native_jpeg_cache_from_heic(self):
        assert self.type == PostType.IMAGE, 'Cannot operate on post of non-IMAGE post type'
        image = self.native_heic_cache.get_image()
        self.native_jpeg_cache.set(image=image)

    def crop_native_jpeg_cache(self):
        assert self.type == PostType.IMAGE, 'Cannot operate on post of non-IMAGE post type'
        assert (crop := self.image_item.get('crop')) , 'Cannot crop post with no crop specified'

        image = self.native_jpeg_cache.get_image()
        cur_width, cur_height = image.size
        ul_x, ul_y = crop['upperLeft']['x'], crop['upperLeft']['y']
        lr_x, lr_y = crop['lowerRight']['x'], crop['lowerRight']['y']

        if lr_y > cur_height:
            raise PostException('Image not tall enough to crop as requested')
        if lr_x > cur_width:
            raise PostException('Image not wide enough to crop as requested')

        try:
            image = image.crop((ul_x, ul_y, lr_x, lr_y))
        except Exception as err:
            raise PostException(f'Unable to crop image for post `{self.id}`: {err}')

        self.native_jpeg_cache.set(image=image)

    def upload_native_image_data_base64(self, image_data):
        "Given a base64-encoded string of image data, set the native image in S3 and our cached copy of the data"
        cache = self.native_heic_cache if self.image_item.get('imageFormat') == 'HEIC' else self.native_jpeg_cache
        cache.set(io.BytesIO(base64.b64decode(image_data)))
        cache.flush()

    def start_processing_video_upload(self):
        assert self.type == PostType.VIDEO, 'Can only process_video_upload() for VIDEO posts'
        assert self.status in (PostStatus.PENDING, PostStatus.ERROR), 'Can only call for PENDING & ERROR posts'

        # mark ourselves as processing
        transacts = [self.dynamo.transact_set_post_status(self.item, PostStatus.PROCESSING)]
        self.dynamo.client.transact_write_items(transacts)
        self.item['postStatus'] = PostStatus.PROCESSING

        # start the media convert job
        input_key = self.get_original_video_path()
        video_output_key_prefix = self.get_hls_video_path_prefix()
        image_output_key_prefix = self.get_poster_video_path_prefix()
        self.mediaconvert_client.create_job(input_key, video_output_key_prefix, image_output_key_prefix)

    def finish_processing_video_upload(self):
        assert self.type == PostType.VIDEO, 'Can only process_video_upload() for VIDEO posts'
        assert self.status == PostStatus.PROCESSING, 'Can only call for PROCESSING posts'

        # make the poster image our new 'native' image
        poster_path = self.get_poster_path()
        native_path = self.get_image_path(image_size.NATIVE)
        self.s3_uploads_client.copy_object(poster_path, native_path)
        self.s3_uploads_client.delete_object(poster_path)

        self.build_image_thumbnails()
        self.complete()

    def error(self):
        if self.status not in (PostStatus.PENDING, PostStatus.PROCESSING):
            raise PostException('Only posts with status PENDING or PROCESSING may transition to ERROR')

        transacts = [self.dynamo.transact_set_post_status(self.item, PostStatus.ERROR)]
        self.dynamo.client.transact_write_items(transacts)

        self.refresh_item(strongly_consistent=True)
        return self

    def complete(self, now=None):
        "Transition the post to COMPLETED status"
        now = now or pendulum.now('utc')

        if self.status in (PostStatus.COMPLETED, PostStatus.ARCHIVED, PostStatus.DELETING):
            msg = f'Refusing to change post `{self.id}` with status `{self.status}` to `{PostStatus.COMPLETED}`'
            raise PostException(msg)

        # Determine the original_post_id, if this post isn't original
        original_post_id = None
        if self.type == PostType.IMAGE:
            # need strongly consistent because checksum may have been just set
            checksum = self.refresh_item(strongly_consistent=True).item['checksum']
            post_id = self.dynamo.get_first_with_checksum(checksum)
            if post_id and post_id != self.id:
                original_post_id = post_id

        set_as_user_photo = self.item.get('setAsUserPhoto')
        album_id = self.item.get('albumId')
        album = self.album_manager.get_album(album_id) if album_id else None
        album_rank = album.get_next_last_rank() if album else None

        # complete the post
        transacts = [
            self.dynamo.transact_set_post_status(
                self.item, PostStatus.COMPLETED, original_post_id=original_post_id, album_rank=album_rank,
            ),
            self.user_manager.dynamo.transact_post_completed(self.user_id),
        ]
        if album:
            old_rank_count = album.item.get('rankCount')
            transacts.append(album.dynamo.transact_add_post(album.id, old_rank_count=old_rank_count, now=now))

        self.dynamo.client.transact_write_items(transacts)
        self.refresh_item(strongly_consistent=True)

        # update the user's profile photo, if needed
        if set_as_user_photo:
            try:
                self.user.update_photo(self.id)
            except UserException as err:
                logger.warning(f'Unable to set user photo with post `{self.id}`: {err}')

        # update the first story if needed
        if self.item.get('expiresAt'):
            self.followed_first_story_manager.refresh_after_story_change(story_now=self.item)

        # add post to feeds
        self.feed_manager.add_post_to_followers_feeds(self.user_id, self.item)

        # update album art if needed
        if album:
            album.update_art_if_needed()

        # give new posts a free bump into trending, but not their user
        self.trending_increment_score(now=now)

        # alert frontend
        self.appsync.trigger_notification(PostNotificationType.COMPLETED, self)

        return self

    def archive(self, forced=False):
        "Transition the post to ARCHIVED status"
        if self.status != PostStatus.COMPLETED:
            raise PostException(f'Cannot archive post with status `{self.status}`')

        album_id = self.item.get('albumId')
        album = self.album_manager.get_album(album_id) if album_id else None

        # set the post as archived
        transacts = [
            self.dynamo.transact_set_post_status(self.item, PostStatus.ARCHIVED),
            self.user_manager.dynamo.transact_post_archived(self.user_id, forced=forced),
        ]
        if album:
            transacts.append(album.dynamo.transact_remove_post(album.id))
        self.dynamo.client.transact_write_items(transacts)
        self.refresh_item(strongly_consistent=True)

        # dislike all likes of the post
        self.like_manager.dislike_all_of_post(self.id)

        # if it was the first followed story, refresh that
        if self.item.get('expiresAt'):
            self.followed_first_story_manager.refresh_after_story_change(story_prev=self.item)

        # delete the trending index, if it exists
        self.trending_delete()

        # update feeds
        self.feed_manager.delete_post_from_followers_feeds(self.user_id, self.id)

        # update album art if needed
        if album:
            album.update_art_if_needed()

        return self

    def restore(self):
        "Transition the post out of ARCHIVED status"
        if self.status != PostStatus.ARCHIVED:
            raise PostException(f'Post `{self.id}` is not archived (has status `{self.status}`)')

        album_id = self.item.get('albumId')
        album = self.album_manager.get_album(album_id) if album_id else None
        album_rank = album.get_next_last_rank() if album else None

        # restore the post
        transacts = [
            self.dynamo.transact_set_post_status(self.item, PostStatus.COMPLETED, album_rank=album_rank),
            self.user_manager.dynamo.transact_post_restored(self.user_id),
        ]
        if album:
            old_rank_count = album.item.get('rankCount')
            transacts.append(self.album_manager.dynamo.transact_add_post(album.id, old_rank_count=old_rank_count))
        self.dynamo.client.transact_write_items(transacts)
        self.refresh_item(strongly_consistent=True)

        # refresh the first story if needed
        if self.item.get('expiresAt'):
            self.followed_first_story_manager.refresh_after_story_change(story_now=self.item)

        # update feeds
        self.feed_manager.add_post_to_followers_feeds(self.user_id, self.item)

        # update album art if needed
        if album:
            album.update_art_if_needed()

        return self

    def delete(self):
        "Delete the post and all its media"

        # we only have to the album if the previous status was COMPLETED
        album = None
        if self.status == PostStatus.COMPLETED:
            if album_id := self.item.get('albumId'):
                album = self.album_manager.get_album(album_id)

        # mark the post and the media as in the deleting process
        prev_post_status = self.status
        transacts = [
            self.dynamo.transact_set_post_status(self.item, PostStatus.DELETING),
            self.user_manager.dynamo.transact_post_deleted(self.user_id, prev_status=self.status),
        ]
        if self.status == PostStatus.COMPLETED and album:
            transacts.append(album.dynamo.transact_remove_post(album.id))
        self.dynamo.client.transact_write_items(transacts)
        self.refresh_item(strongly_consistent=True)

        # dislike all likes of the post
        self.like_manager.dislike_all_of_post(self.id)

        # delete all comments on the post
        self.comment_manager.delete_all_on_post(self.id)

        # if it was the first followed story, refresh that
        if self.item.get('expiresAt'):
            self.followed_first_story_manager.refresh_after_story_change(story_prev=self.item)

        # remove it from feeds, user post count
        if prev_post_status == PostStatus.COMPLETED:
            self.feed_manager.delete_post_from_followers_feeds(self.user_id, self.id)

        # delete any post views of it
        self.delete_views()

        # delete the trending index, if it exists
        self.trending_delete()

        # update album art, if needed
        if album:
            album.update_art_if_needed()

        # do the deletes for real
        self.s3_uploads_client.delete_objects_with_prefix(self.s3_prefix)
        if self.image_item:
            self.image_dynamo.delete(self.id)
        self.flag_dynamo.delete_all_for_item(self.id)
        self.original_metadata_dynamo.delete(self.id)
        self.dynamo.delete_post(self.id)

        return self

    def set(
        self,
        text=None,
        comments_disabled=None,
        likes_disabled=None,
        sharing_disabled=None,
        verification_hidden=None,
    ):
        args = [text, comments_disabled, likes_disabled, sharing_disabled, verification_hidden]
        if all(v is None for v in args):
            raise PostException('Empty edit requested')

        if self.type == PostType.TEXT_ONLY and text == '':
            raise PostException('Cannot set text to null on text-only post')

        text_tags = self.user_manager.get_text_tags(text) if text is not None else None
        self.item = self.dynamo.set(
            self.id,
            text=text,
            text_tags=text_tags,
            comments_disabled=comments_disabled,
            likes_disabled=likes_disabled,
            sharing_disabled=sharing_disabled,
            verification_hidden=verification_hidden,
        )
        return self

    def set_height_and_width(self):
        width, height = self.native_jpeg_cache.get_image().size
        self._image_item = self.image_dynamo.set_height_and_width(self.id, height, width)
        return self

    def set_colors(self):
        try:
            colors = colorthief.ColorThief(self.native_jpeg_cache.get_fh()).get_palette(color_count=5)
        except Exception as err:
            logger.warning(f'ColorTheif failed to get palette with error `{err}` for post `{self.id}`')
        else:
            self._image_item = self.image_dynamo.set_colors(self.id, colors)
        return self

    def set_checksum(self):
        path = self.get_image_path(image_size.NATIVE)
        checksum = self.s3_uploads_client.get_object_checksum(path)
        self.item = self.dynamo.set_checksum(self.id, self.item['postedAt'], checksum)
        return self

    def set_is_verified(self):
        assert self.image_item
        path = self.get_image_path(image_size.NATIVE)
        image_url = self.cloudfront_client.generate_presigned_url(path, ['GET', 'HEAD'])
        is_verified = self.post_verification_client.verify_image(
            image_url,
            image_format=self.image_item.get('imageFormat'),
            original_format=self.image_item.get('originalFormat'),
            taken_in_real=self.image_item.get('takenInReal'),
        )
        self.item = self.dynamo.set_is_verified(self.id, is_verified)
        return self

    def set_expires_at(self, expires_at):
        prev_item = self.item.copy() if 'expiresAt' in self.item else None
        if expires_at:
            self.item = self.dynamo.set_expires_at(self.item, expires_at)
        else:
            self.item = self.dynamo.remove_expires_at(self.id)
        now_item = self.item.copy() if 'expiresAt' in self.item else None
        if prev_item or now_item:
            self.followed_first_story_manager.refresh_after_story_change(story_prev=prev_item, story_now=now_item)
        return self

    def set_album(self, album_id):
        "Set the album the post is in. Set album_id to None to remove the post from all albums."
        prev_album_id = self.item.get('albumId')

        if prev_album_id == album_id:
            return self

        # if an album is specified, verify it exists and is ours
        album = self.album_manager.get_album(album_id) if album_id else None
        album_rank = album.get_next_last_rank() if album and self.status == PostStatus.COMPLETED else None
        if album_id:
            if not album:
                raise PostException(f'Album `{album_id}` does not exist')
            if album.user_id != self.user_id:
                msg = f'Album `{album_id}` and post `{self.id}` belong to different users'
                raise PostException(msg)

        transacts = [self.dynamo.transact_set_album_id(self.item, album_id, album_rank=album_rank)]
        if self.status == PostStatus.COMPLETED:
            if prev_album_id:
                transacts.append(self.album_manager.dynamo.transact_remove_post(prev_album_id))
            if album:
                old_rank_count = album.item.get('rankCount')
                transacts.append(album.dynamo.transact_add_post(album.id, old_rank_count=old_rank_count))

        self.dynamo.client.transact_write_items(transacts)
        self.refresh_item(strongly_consistent=True)

        # update album art, if needed
        if prev_album_id:
            prev_album = self.album_manager.get_album(prev_album_id)
            if prev_album:
                prev_album.update_art_if_needed()
        if album:
            album.update_art_if_needed()

        return self

    def set_album_order(self, preceding_post_id):
        album_id = self.item.get('albumId')
        if not album_id:
            raise PostException(f'Post `{self.id}` is not in an album')

        preceding_post = None
        if preceding_post_id:
            preceding_post = self.post_manager.get_post(preceding_post_id)

            if not preceding_post:
                raise PostException(f'Preceding post `{preceding_post_id}` does not exist')

            if preceding_post.user_id != self.user_id:
                raise PostException(f'Preceding post `{preceding_post_id}` does not belong to caller')

            if preceding_post.item.get('albumId') != album_id:
                raise PostException(f'Preceding post `{preceding_post_id}` is not in album post is in')

        # determine the post's new rank
        album = self.album_manager.get_album(album_id)
        if preceding_post:
            before_rank = preceding_post.item['gsiK3SortKey']
            after_post_id = next(self.dynamo.generate_post_ids_in_album(album_id, after_rank=before_rank), None)
            if after_post_id:
                # putting the post in between two posts
                after_post = self.post_manager.get_post(after_post_id)
                after_rank = after_post.item['gsiK3SortKey']
                album_rank = (before_rank + after_rank) / 2
            else:
                # putting the post at the back
                album_rank = album.get_next_last_rank()
        else:
            # putting the post at the front
            album_rank = album.get_next_first_rank()

        transacts = [
            self.dynamo.transact_set_album_rank(self.id, album_rank),
            album.dynamo.transact_increment_rank_count(album.id, album.item['rankCount']),
        ]
        self.dynamo.client.transact_write_items(transacts)
        self.item['gsiK3SortKey'] = album_rank

        album.update_art_if_needed()
        return self

    def flag(self, user):
        # if the post is from a private user then we must be a follower to flag the post
        posted_by_user = self.user_manager.get_user(self.user_id)
        if posted_by_user.item['privacyStatus'] != UserPrivacyStatus.PUBLIC:
            follow = self.follower_manager.get_follow(user.id, self.user_id)
            if not follow or follow.status != FollowStatus.FOLLOWING:
                raise PostException(f'User does not have access to post `{self.id}`')

        super().flag(user)
        return self

    def remove_from_flagging(self):
        self.archive(forced=True)

    def is_user_forced_disabling_criteria_met(self):
        return self.user.is_forced_disabling_criteria_met_by_posts()

    def record_view_count(self, user_id, view_count, viewed_at=None):
        if self.status != PostStatus.COMPLETED:
            logger.warning(f'Cannot record views by user `{user_id}` on non-COMPLETED post `{self.id}`')
            return False

        # record user's view of their own post, but don't increment any counters about it
        # their view will be filtered out when looking at Post.viewedBy
        is_new_view = super().record_view_count(user_id, view_count, viewed_at=viewed_at)

        if self.user_id == user_id:
            self.dynamo.clear_comments_unviewed_count(self.id)
            self.card_manager.remove_card_by_spec_if_exists(CommentCardSpec(user_id, self.id))
            self.dynamo.set_last_unviewed_comment_at(self.item, None)
            return False  # post owner's views don't count for trending, etc.

        recorded = self.trending_increment_score(now=viewed_at)
        if recorded:
            self.user.trending_increment_score(now=viewed_at)

        # record the viewedBy on the post and user
        if is_new_view:
            self.dynamo.increment_viewed_by_count(self.id)
            self.user_manager.dynamo.increment_post_viewed_by_count(self.user_id)

        # If this is a non-original post, count this like a view of the original post as well
        if self.original_post_id != self.id:
            original_post = self.post_manager.get_post(self.original_post_id)
            if original_post:
                original_post.record_view_count(user_id, view_count, viewed_at=viewed_at)

        return True

    def trending_increment_score(self, now=None, **kwargs):
        now = now or pendulum.now('utc')

        # keep non-verified posts out of trending
        if self.type == PostType.IMAGE and not self.is_verified:
            return False

        # keep non-original posts out of trending
        if self.type == PostType.IMAGE and self.original_post_id != self.id:
            return False

        # keep the 'real' user's posts out of trending
        if self.user_id == self.user_manager.real_user_id:
            return False

        # posts over 24 hours old don't earn more trending points
        if now - self.posted_at > pendulum.duration(hours=24):
            return False

        return super().trending_increment_score(now=now, **kwargs)
