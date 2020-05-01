import base64
from io import BytesIO
import logging

from colorthief import ColorThief
import pendulum
from PIL import Image, ImageOps
import pyheif

from app.models.user.enums import UserStatus
from app.utils import image_size

from . import enums, exceptions
from .enums import PostStatus, PostType, PostNotificationType
from .text_image import generate_text_image

logger = logging.getLogger()


class Post:

    jpeg_content_type = 'image/jpeg'
    heic_content_type = 'image/heic'

    enums = enums
    exceptions = exceptions

    # users that have flag admin power: posts they flag are immediately archived
    flag_admin_usernames = ('real', 'ian')

    def __init__(self, item, post_appsync=None, post_dynamo=None, post_flag_dynamo=None, post_image_dynamo=None,
                 post_original_metadata_dynamo=None, cloudfront_client=None, mediaconvert_client=None,
                 post_verification_client=None, s3_uploads_client=None, album_manager=None, block_manager=None,
                 comment_manager=None, feed_manager=None, follow_manager=None, followed_first_story_manager=None,
                 like_manager=None, post_manager=None, trending_manager=None, user_manager=None,
                 view_manager=None):
        if post_appsync:
            self.appsync = post_appsync
        if post_dynamo:
            self.dynamo = post_dynamo
        if post_flag_dynamo:
            self.flag_dynamo = post_flag_dynamo
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
        if comment_manager:
            self.comment_manager = comment_manager
        if feed_manager:
            self.feed_manager = feed_manager
        if follow_manager:
            self.follow_manager = follow_manager
        if followed_first_story_manager:
            self.followed_first_story_manager = followed_first_story_manager
        if like_manager:
            self.like_manager = like_manager
        if post_manager:
            self.post_manager = post_manager
        if trending_manager:
            self.trending_manager = trending_manager
        if user_manager:
            self.user_manager = user_manager
        if view_manager:
            self.view_manager = view_manager

        self.item = item
        # immutables
        self.id = item['postId']
        self.type = self.item['postType']
        self.user_id = item['postedByUserId']

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

    def refresh_item(self, strongly_consistent=False):
        self.item = self.dynamo.get_post(self.id, strongly_consistent=strongly_consistent)
        return self

    def refresh_image_item(self):
        self._image_item = self.image_dynamo.get(self.id) or next(self.image_dynamo.generate_by_post(self.id), None)
        return self

    def get_s3_image_path(self, size):
        "From within the user's directory, return the path to the s3 object of the requested size"
        return '/'.join([self.item['postedByUserId'], 'post', self.item['postId'], 'image', size.filename])

    def get_native_image_buffer(self):
        if not hasattr(self, '_native_image_data'):
            if self.type == PostType.TEXT_ONLY:
                max_dims = image_size.K4.max_dimensions
                self._native_image_data = generate_text_image(self.item['text'], max_dims).read()

            elif self.type in (PostType.IMAGE, PostType.VIDEO):
                path = self.get_image_path(image_size.NATIVE)
                try:
                    self._native_image_data = self.s3_uploads_client.get_object_data_stream(path).read()
                except self.s3_uploads_client.exceptions.NoSuchKey:
                    raise exceptions.PostException(f'Native image buffer not found for post `{self.id}`')

            else:
                raise Exception(f'Unexpected post type `{self.type}` for post `{self.id}`')

        return BytesIO(self._native_image_data)

    def get_1080p_image_buffer(self):
        if not hasattr(self, '_1080p_image_data'):
            if self.type == PostType.TEXT_ONLY:
                max_dims = image_size.P1080.max_dimensions
                self._1080p_image_data = generate_text_image(self.item['text'], max_dims).read()

            elif self.type in (PostType.IMAGE, PostType.VIDEO):
                path = self.get_image_path(image_size.P1080)
                try:
                    self._1080p_image_data = self.s3_uploads_client.get_object_data_stream(path).read()
                except self.s3_uploads_client.exceptions.NoSuchKey:
                    raise exceptions.PostException(f'1080p image buffer not found for post `{self.id}`')

            else:
                raise Exception(f'Unexpected post type `{self.type}` for post `{self.id}`')

        return BytesIO(self._1080p_image_data)

    def get_original_video_path(self):
        return f'{self.s3_prefix}/{enums.VIDEO_ORIGINAL_FILENAME}'

    def get_poster_video_path_prefix(self):
        return f'{self.s3_prefix}/{enums.VIDEO_POSTER_PREFIX}'

    def get_poster_path(self):
        return f'{self.s3_prefix}/{enums.VIDEO_POSTER_PREFIX}.0000000.jpg'

    def get_image_path(self, size):
        return f'{self.s3_prefix}/{enums.IMAGE_DIR}/{size.filename}'

    def get_hls_video_path_prefix(self):
        return f'{self.s3_prefix}/{enums.VIDEO_HLS_PREFIX}'

    def get_hls_master_m3u8_url(self):
        path = f'{self.s3_prefix}/{enums.VIDEO_HLS_PREFIX}.m3u8'
        return self.cloudfront_client.generate_unsigned_url(path)

    def get_hls_access_cookies(self, expires_at=None):
        expires_at = expires_at or pendulum.now('utc') + pendulum.duration(hours=1)
        s3_path = self.get_hls_video_path_prefix()
        signature_path = s3_path + '*'
        cookie_path = '/' + '/'.join(s3_path.split('/')[:-1]) + '/'  # remove trailing partial filename
        cookies = self.cloudfront_client.generate_presigned_cookies(signature_path, expires_at=expires_at)
        return {
            'domain': self.cloudfront_client.domain,
            'path': cookie_path,
            'expiresAt': expires_at.to_iso8601_string(),
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
        native_buffer = self.get_native_image_buffer()
        try:
            image = ImageOps.exif_transpose(Image.open(native_buffer))
        except Exception as err:
            raise exceptions.PostException(f'Unable to open image data as jpeg for post `{self.id}`: {err}')
        for size in image_size.THUMBNAILS:  # ordered by decreasing size
            in_mem_file = BytesIO()
            try:
                image.thumbnail(size.max_dimensions, resample=Image.LANCZOS)
                image.save(in_mem_file, format='JPEG', quality=100, icc_profile=image.info.get('icc_profile'))
            except Exception as err:
                raise exceptions.PostException(f'Unable to thumbnail image data as jpeg for post `{self.id}`: {err}')
            in_mem_file.seek(0)
            path = self.get_image_path(size)
            self.s3_uploads_client.put_object(path, in_mem_file.read(), self.jpeg_content_type)

    def process_image_upload(self, image_data=None, now=None):
        assert self.type == PostType.IMAGE, 'Can only process_image_upload() for IMAGE posts'
        assert self.status in (PostStatus.PENDING, PostStatus.ERROR), \
            'Can only process_image_upload() for PENDING & ERROR posts'
        now = now or pendulum.now('utc')

        # mark ourselves as processing
        transacts = [self.dynamo.transact_set_post_status(self.item, PostStatus.PROCESSING)]
        self.dynamo.client.transact_write_items(transacts)
        self.item['postStatus'] = PostStatus.PROCESSING

        if image_data:
            # s3 trigger is a no-op because we are already in PROCESSING
            self.upload_native_image_data_base64(image_data)

        if self.image_item.get('imageFormat') == 'HEIC':
            self.set_native_jpeg()

        self.build_image_thumbnails()
        self.set_height_and_width()
        self.set_colors()
        self.set_is_verified()
        self.set_checksum()
        self.complete(now=now)

    def upload_native_image_data_base64(self, image_data):
        "Given a base64-encoded string of image data, set the native image in S3 and our cached copy of the data"
        content_type = self.jpeg_content_type
        size = image_size.NATIVE
        if self.image_item.get('imageFormat') == 'HEIC':
            content_type = self.heic_content_type
            size = image_size.NATIVE_HEIC

        path = self.get_image_path(size)
        image_buffer = BytesIO(base64.b64decode(image_data))
        self.s3_uploads_client.put_object(path, image_buffer, content_type)

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
            raise exceptions.PostException('Only posts with status PENDING or PROCESSING may transition to ERROR')

        transacts = [self.dynamo.transact_set_post_status(self.item, PostStatus.ERROR)]
        self.dynamo.client.transact_write_items(transacts)

        self.refresh_item(strongly_consistent=True)
        return self

    def complete(self, now=None):
        "Transition the post to COMPLETED status"
        now = now or pendulum.now('utc')

        if self.status in (PostStatus.COMPLETED, PostStatus.ARCHIVED, PostStatus.DELETING):
            msg = f'Refusing to change post `{self.id}` with status `{self.status}` to `{PostStatus.COMPLETED}`'
            raise exceptions.PostException(msg)

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
            except self.user.exceptions.UserException as err:
                logger.warning(f'Unable to set user photo with post `{self.id}`: {err}')

        # update the first story if needed
        if self.item.get('expiresAt'):
            self.followed_first_story_manager.refresh_after_story_change(story_now=self.item)

        # add post to feeds
        self.feed_manager.add_post_to_followers_feeds(self.user_id, self.item)

        # update album art if needed
        if album:
            album.update_art_if_needed()

        # alert frontend
        self.appsync.trigger_notification(PostNotificationType.COMPLETED, self)

        return self

    def archive(self, forced=False):
        "Transition the post to ARCHIVED status"
        if self.status != PostStatus.COMPLETED:
            raise exceptions.PostException(f'Cannot archive post with status `{self.status}`')

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
        self.trending_manager.dynamo.delete_trending(self.id)

        # update feeds
        self.feed_manager.delete_post_from_followers_feeds(self.user_id, self.id)

        # update album art if needed
        if album:
            album.update_art_if_needed()

        return self

    def restore(self):
        "Transition the post out of ARCHIVED status"
        if self.status != PostStatus.ARCHIVED:
            raise exceptions.PostException(f'Post `{self.id}` is not archived (has status `{self.status}`)')

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
        self.view_manager.delete_views(self.item['partitionKey'])

        # delete the trending index, if it exists
        self.trending_manager.dynamo.delete_trending(self.id)

        # update album art, if needed
        if album:
            album.update_art_if_needed()

        # do the deletes for real
        self.s3_uploads_client.delete_objects_with_prefix(self.s3_prefix)
        if self.image_item:
            self.dynamo.client.delete_item_by_pk(self.image_item)
        self.flag_dynamo.delete_all_for_post(self.id)
        self.original_metadata_dynamo.delete(self.id)
        self.dynamo.delete_post(self.id)

        return self

    def set(self, text=None, comments_disabled=None, likes_disabled=None, sharing_disabled=None,
            verification_hidden=None):
        args = [text, comments_disabled, likes_disabled, sharing_disabled, verification_hidden]
        if all(v is None for v in args):
            raise exceptions.PostException('Empty edit requested')

        if self.type == PostType.TEXT_ONLY and text == '':
            raise exceptions.PostException('Cannot set text to null on text-only post')

        text_tags = self.user_manager.get_text_tags(text) if text is not None else None
        self.item = self.dynamo.set(
            self.id, text=text, text_tags=text_tags, comments_disabled=comments_disabled,
            likes_disabled=likes_disabled, sharing_disabled=sharing_disabled,
            verification_hidden=verification_hidden,
        )
        return self

    def set_native_jpeg(self):
        "From a native HEIC, upload a native jpeg"
        heic_path = self.get_image_path(image_size.NATIVE_HEIC)
        heic_data_stream = self.s3_uploads_client.get_object_data_stream(heic_path)
        try:
            heif_file = pyheif.read_heif(heic_data_stream)
        except pyheif.error.HeifError as err:
            raise exceptions.PostException(f'Unable to read HEIC file for post `{self.id}`: {err}')
        image = Image.frombytes(mode=heif_file.mode, size=heif_file.size, data=heif_file.data)
        in_mem_file = BytesIO()
        image.save(in_mem_file, format='JPEG', quality=100, icc_profile=image.info.get('icc_profile'))
        in_mem_file.seek(0)
        jpeg_path = self.get_image_path(image_size.NATIVE)
        self.s3_uploads_client.put_object(jpeg_path, in_mem_file.read(), self.jpeg_content_type)

    def set_height_and_width(self):
        image = Image.open(self.get_native_image_buffer())
        width, height = image.size
        self._image_item = self.image_dynamo.set_height_and_width(self.id, self.image_item.get('mediaId'), height,
                                                                  width)
        return self

    def set_colors(self):
        native_buffer = self.get_native_image_buffer()
        try:
            colors = ColorThief(native_buffer).get_palette(color_count=5)
        except Exception as err:
            logger.warning(f'ColorTheif failed to calculate color palette with error `{err}` for post `{self.id}`')
        else:
            self._image_item = self.image_dynamo.set_colors(self.id, self.image_item.get('mediaId'), colors)
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
            image_url, image_format=self.image_item.get('imageFormat'),
            original_format=self.image_item.get('originalFormat'), taken_in_real=self.image_item.get('takenInReal'),
        )
        self.item = self.dynamo.set_is_verified(self.id, is_verified)
        return self

    def set_new_comment_activity(self, new_value):
        old_value = self.item.get('hasNewCommentActivity', False)
        if old_value == new_value:
            return self

        # order matters to moto (in test suite), but not on dynamo
        transacts = [self.dynamo.transact_set_has_new_comment_activity(self.id, new_value)]
        transact_exceptions = [exceptions.DoesNotHaveExpectedCommentActivity(self.id, old_value)]

        user_dyanmo = self.user_manager.dynamo
        if new_value:
            transacts.append(user_dyanmo.transact_increment_post_has_new_comment_activity_count(self.user_id))
        else:
            transacts.append(user_dyanmo.transact_decrement_post_has_new_comment_activity_count(self.user_id))
        transact_exceptions.append(exceptions.PostException(
            f'Unable to increment/decrement posts have new comment activity count for user `{self.user_id}`',
        ))

        try:
            self.dynamo.client.transact_write_items(transacts, transact_exceptions)
        except exceptions.DoesNotHaveExpectedCommentActivity:
            # race condition, another thread already set the comment activity so we don't need to
            pass

        # avoid another refresh_item b/c of possible race conditions
        self.item['hasNewCommentActivity'] = new_value
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
                raise exceptions.PostException(f'Album `{album_id}` does not exist')
            if album.user_id != self.user_id:
                msg = f'Album `{album_id}` and post `{self.id}` belong to different users'
                raise exceptions.PostException(msg)

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
            raise exceptions.PostException(f'Post `{self.id}` is not in an album')

        preceding_post = None
        if preceding_post_id:
            preceding_post = self.post_manager.get_post(preceding_post_id)

            if not preceding_post:
                raise exceptions.PostException(f'Preceding post `{preceding_post_id}` does not exist')

            if preceding_post.user_id != self.user_id:
                raise exceptions.PostException(f'Preceding post `{preceding_post_id}` does not belong to caller')

            if preceding_post.item.get('albumId') != album_id:
                raise exceptions.PostException(f'Preceding post `{preceding_post_id}` is not in album post is in')

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
        # can't flag a post of a user that has blocked us
        if self.block_manager.is_blocked(self.user_id, user.id):
            raise exceptions.PostException(f'User has been blocked by owner of post `{self.id}`')

        # can't flag a post of a user we have blocked
        if self.block_manager.is_blocked(user.id, self.user_id):
            raise exceptions.PostException(f'User has blocked owner of post `{self.id}`')

        # cant flag our own post
        if user.id == self.user_id:
            raise exceptions.PostException(f'User cant flag their own post `{self.id}`')

        # if the post is from a private user then we must be a follower to flag the post
        posted_by_user = self.user_manager.get_user(self.user_id)
        if posted_by_user.item['privacyStatus'] != self.user_manager.enums.UserPrivacyStatus.PUBLIC:
            follow = self.follow_manager.get_follow(user.id, self.user_id)
            if not follow or follow.status != self.follow_manager.enums.FollowStatus.FOLLOWING:
                raise exceptions.PostException(f'User does not have access to post `{self.id}`')

        transacts = [
            self.flag_dynamo.transact_add(self.id, user.id),
            self.dynamo.transact_increment_flag_count(self.id),
        ]
        transact_exceptions = [exceptions.AlreadyFlagged(self.id, user.id), exceptions.PostDoesNotExist(self.id)]
        self.dynamo.client.transact_write_items(transacts, transact_exceptions)
        self.item['flagCount'] = self.item.get('flagCount', 0) + 1

        # force archive the post?
        if user.username in self.flag_admin_usernames or self.is_crowdsourced_forced_archiving_criteria_met():
            logger.warning(f'Force archiving post `{self.id}`')
            self.archive(forced=True)

            # force disable the user?
            self.user.refresh_item(strongly_consistent=True)
            if self.user.is_forced_disabling_criteria_met():
                logger.warning(f'Force disabling user `{self.user.id}`')
                self.user.set_user_status(UserStatus.DISABLED)
                # the string USER_FORCE_DISABLED is hooked up to a cloudwatch metric & alert
                logger.warning(f'USER_FORCE_DISABLED: user `{self.user.id}` with username `{self.user.username}`')

        return self

    def unflag(self, user_id):
        transacts = [
            self.flag_dynamo.transact_delete(self.id, user_id),
            self.dynamo.transact_decrement_flag_count(self.id),
        ]
        transact_exceptions = [
            exceptions.NotFlagged(self.id, user_id),
            exceptions.PostException(f'Post `{self.id}` does not exist or has no flagCount'),
        ]
        self.dynamo.client.transact_write_items(transacts, transact_exceptions)

        self.item['flagCount'] = self.item.get('flagCount', 0) - 1
        return self

    def is_crowdsourced_forced_archiving_criteria_met(self):
        # the post should be force-archived if (directly from spec):
        #   - over 5 users have viewed the post and
        #   - at least 10% of them have flagged it
        viewed_by_count = self.item.get('viewedByCount', 0)
        flag_count = self.item.get('flagCount', 0)
        if viewed_by_count > 5 and flag_count > viewed_by_count / 10:
            return True
        return False
