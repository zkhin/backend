from io import BytesIO
import logging

import pendulum
from PIL import Image, ImageOps

from app.models.media.enums import MediaStatus
from app.utils import image_size

from . import enums, exceptions
from .enums import FlagStatus, PostStatus, PostType
from .text_image import generate_text_image

logger = logging.getLogger()


class Post:

    jpeg_content_type = 'image/jpeg'

    enums = enums
    exceptions = exceptions
    FlagStatus = FlagStatus

    def __init__(self, item, post_dynamo, cloudfront_client=None, mediaconvert_client=None, s3_uploads_client=None,
                 feed_manager=None, like_manager=None, media_manager=None, view_manager=None, user_manager=None,
                 comment_manager=None, flag_manager=None, album_manager=None, followed_first_story_manager=None,
                 trending_manager=None, post_manager=None):
        self.dynamo = post_dynamo

        if cloudfront_client:
            self.cloudfront_client = cloudfront_client
        if mediaconvert_client:
            self.mediaconvert_client = mediaconvert_client
        if s3_uploads_client:
            self.s3_uploads_client = s3_uploads_client
        if album_manager:
            self.album_manager = album_manager
        if comment_manager:
            self.comment_manager = comment_manager
        if feed_manager:
            self.feed_manager = feed_manager
        if flag_manager:
            self.flag_manager = flag_manager
        if followed_first_story_manager:
            self.followed_first_story_manager = followed_first_story_manager
        if like_manager:
            self.like_manager = like_manager
        if media_manager:
            self.media_manager = media_manager
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
    def s3_prefix(self):
        return '/'.join([self.user_id, 'post', self.id])

    def refresh_item(self, strongly_consistent=False):
        self.item = self.dynamo.get_post(self.id, strongly_consistent=strongly_consistent)
        return self

    def get_native_image_buffer(self):
        if self.status == PostStatus.PENDING:
            raise exceptions.PostException(f'No native image buffer for {PostStatus.PENDING} post `{self.id}``')

        if not hasattr(self, '_native_image_data'):
            if self.type == PostType.TEXT_ONLY:
                max_dims = image_size.K4.max_dimensions
                self._native_image_data = generate_text_image(self.item['text'], max_dims).read()

            elif self.type == PostType.VIDEO:
                path = self.get_image_path(image_size.NATIVE)
                self._native_image_data = self.s3_uploads_client.get_object_data_stream(path).read()

            elif self.type == PostType.IMAGE:
                media_item = next(self.media_manager.dynamo.generate_by_post(self.id, uploaded=True), None)
                if not media_item:
                    # shouldn't get here, as the post should be in completed state and have media
                    raise Exception(f'Did not find uploaded media for post `{self.id}`')
                path = self.media_manager.init_media(media_item).get_s3_path(image_size.NATIVE)
                self._native_image_data = self.s3_uploads_client.get_object_data_stream(path).read()

            else:
                raise Exception(f'Unexpected post type `{self.type}` for post `{self.id}`')

        return BytesIO(self._native_image_data)

    def get_1080p_image_buffer(self):
        if self.status == PostStatus.PENDING:
            raise exceptions.PostException(f'No 1080p image buffer for {PostStatus.PENDING} post `{self.id}``')

        if not hasattr(self, '_1080p_image_data'):
            if self.type == PostType.TEXT_ONLY:
                max_dims = image_size.P1080.max_dimensions
                self._1080p_image_data = generate_text_image(self.item['text'], max_dims).read()

            elif self.type == PostType.VIDEO:
                path = self.get_image_path(image_size.P1080)
                self._1080p_image_data = self.s3_uploads_client.get_object_data_stream(path).read()

            elif self.type == PostType.IMAGE:
                media_item = next(self.media_manager.dynamo.generate_by_post(self.id, uploaded=True), None)
                if not media_item:
                    # shouldn't get here, as the post should be in completed state and have media
                    raise Exception(f'Did not find uploaded media for post `{self.id}`')
                path = self.media_manager.init_media(media_item).get_s3_path(image_size.P1080)
                self._1080p_image_data = self.s3_uploads_client.get_object_data_stream(path).read()

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

    def delete_s3_video(self):
        path = self.get_original_video_path()
        self.s3_uploads_client.delete_object(path)

    def serialize(self, caller_user_id):
        resp = self.item.copy()
        user = self.user_manager.get_user(self.user_id)
        resp['postedBy'] = user.serialize(caller_user_id)
        return resp

    def build_image_thumbnails(self):
        image = Image.open(self.get_native_image_buffer())
        image = ImageOps.exif_transpose(image)
        for size in image_size.THUMBNAILS:  # ordered by decreasing size
            image.thumbnail(size.max_dimensions, resample=Image.LANCZOS)
            in_mem_file = BytesIO()
            image.save(in_mem_file, format='JPEG')
            in_mem_file.seek(0)
            path = self.get_image_path(size)
            self.s3_uploads_client.put_object(path, in_mem_file.read(), self.jpeg_content_type)

    def process_image_upload(self, media=None):
        assert self.type == PostType.IMAGE, 'Can only process_image_upload() for IMAGE posts'
        assert self.status in (PostStatus.PENDING, PostStatus.ERROR), \
            'Can only process_image_upload() for PENDING & ERROR posts'
        assert media, 'For now, Post.process_image_upload() must be called with media'

        # mark ourselves as processing
        transacts = [self.dynamo.transact_set_post_status(self.item, PostStatus.PROCESSING)]
        self.dynamo.client.transact_write_items(transacts)
        self.item['postStatus'] = PostStatus.PROCESSING

        # let any exceptions flow through up the chain
        media.process_upload()
        self.complete()

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

    def error(self, media=None):
        if self.status not in (PostStatus.PENDING, PostStatus.PROCESSING):
            raise exceptions.PostException('Only posts with status PENDING or PROCESSING may transition to ERROR')

        transacts = [self.dynamo.transact_set_post_status(self.item, PostStatus.ERROR)]
        if media:
            transacts.append(media.dynamo.transact_set_status(media.item, media.enums.MediaStatus.ERROR))

        self.dynamo.client.transact_write_items(transacts)
        self.refresh_item(strongly_consistent=True)
        if media:
            media.refresh_item(strongly_consistent=True)
        return self

    def complete(self, now=None):
        "Transition the post to COMPLETED status"
        now = now or pendulum.now('utc')

        if self.status in (PostStatus.COMPLETED, PostStatus.ARCHIVED, PostStatus.DELETING):
            msg = f'Refusing to change post `{self.id}` with status `{self.status}` to `{PostStatus.COMPLETED}`'
            raise exceptions.PostException(msg)

        # Determine the original_post_id, if this post isn't original
        # Note that in order to simplify the problem and focus on the use case that matters,
        # we declare that only posts with exactly one media item may be non-original.
        # That is to say, text-only posts or multiple-media posts will never have originalPostId set.
        original_post_id = None
        media_items = list(self.media_manager.dynamo.generate_by_post(self.id))
        media_item = (
            # need strongly consistent because checksum was potentially just set
            self.media_manager.dynamo.get_media(media_items[0]['mediaId'], strongly_consistent=True)
            if media_items else None
        )
        if media_item:
            first_media_id = self.media_manager.dynamo.get_first_media_id_with_checksum(media_item['checksum'])
            if first_media_id and first_media_id != media_item['mediaId']:
                first_media_item = self.media_manager.dynamo.get_media(first_media_id)
                original_post_id = first_media_item['postId'] if first_media_item else None

        album_id = self.item.get('albumId')
        album = self.album_manager.get_album(album_id) if album_id else None
        album_rank = album.get_next_last_rank() if album else None

        # complete the post
        transacts = [
            self.dynamo.transact_set_post_status(
                self.item, PostStatus.COMPLETED, original_post_id=original_post_id, album_rank=album_rank,
            ),
            self.user_manager.dynamo.transact_increment_post_count(self.user_id),
        ]
        if album:
            old_rank_count = album.item.get('rankCount')
            transacts.append(album.dynamo.transact_add_post(album.id, old_rank_count=old_rank_count, now=now))

        self.dynamo.client.transact_write_items(transacts)
        self.refresh_item(strongly_consistent=True)

        # update the first story if needed
        if self.item.get('expiresAt'):
            self.followed_first_story_manager.refresh_after_story_change(story_now=self.item)

        # add post to feeds
        self.feed_manager.add_post_to_followers_feeds(self.user_id, self.item)

        # update album art if needed
        if album:
            album.update_art_if_needed()

        return self

    def archive(self):
        "Transition the post to ARCHIVED status"
        if self.status != PostStatus.COMPLETED:
            raise exceptions.PostException(f'Cannot archive post with status `{self.status}`')

        album_id = self.item.get('albumId')
        album = self.album_manager.get_album(album_id) if album_id else None

        # archive the post and its media objects
        transacts = [
            self.dynamo.transact_set_post_status(self.item, PostStatus.ARCHIVED),
            self.user_manager.dynamo.transact_decrement_post_count(self.user_id),
        ]
        if album:
            transacts.append(album.dynamo.transact_remove_post(album.id))

        media_items = []
        for media_item in self.media_manager.dynamo.generate_by_post(self.id):
            transacts.append(self.media_manager.dynamo.transact_set_status(media_item, MediaStatus.ARCHIVED))
            media_items.append(media_item)

        self.dynamo.client.transact_write_items(transacts)

        # update in-memory copy of dynamo state
        self.refresh_item(strongly_consistent=True)
        self.item['mediaObjects'] = [
            self.media_manager.dynamo.get_media(media_item['mediaId'], strongly_consistent=True)
            for media_item in media_items
        ]

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
            self.user_manager.dynamo.transact_increment_post_count(self.user_id),
        ]

        if album:
            old_rank_count = album.item.get('rankCount')
            transacts.append(self.album_manager.dynamo.transact_add_post(album.id, old_rank_count=old_rank_count))

        media_items = list(self.media_manager.dynamo.generate_by_post(self.id))
        for media_item in media_items:
            transacts.append(self.media_manager.dynamo.transact_set_status(media_item, MediaStatus.UPLOADED))

        self.dynamo.client.transact_write_items(transacts)

        # update in-memory copy of dynamo state
        self.refresh_item(strongly_consistent=True)
        self.item['mediaObjects'] = [
            self.media_manager.dynamo.get_media(media_item['mediaId'], strongly_consistent=True)
            for media_item in media_items
        ]

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
        media_items = []
        transacts = [self.dynamo.transact_set_post_status(self.item, PostStatus.DELETING)]
        if self.status == PostStatus.COMPLETED:
            transacts.append(self.user_manager.dynamo.transact_decrement_post_count(self.user_id))
            if album:
                transacts.append(album.dynamo.transact_remove_post(album.id))

        for media_item in self.media_manager.dynamo.generate_by_post(self.id):
            transacts.append(self.media_manager.dynamo.transact_set_status(media_item, MediaStatus.DELETING))
            media_items.append(media_item)

        self.dynamo.client.transact_write_items(transacts)

        # update in-memory copy of dynamo state
        prev_post_status = self.status
        self.refresh_item(strongly_consistent=True)
        self.item['mediaObjects'] = [
            self.media_manager.dynamo.get_media(media_item['mediaId'], strongly_consistent=True)
            for media_item in media_items
        ]

        # dislike all likes of the post
        self.like_manager.dislike_all_of_post(self.id)

        # delete all comments on the post
        self.comment_manager.delete_all_on_post(self.id)

        # unflag all flags of the post
        self.flag_manager.unflag_all_on_post(self.id)

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
        for media_item in self.item['mediaObjects']:
            self.dynamo.client.delete_item_by_pk(media_item)
        self.dynamo.client.delete_item_by_pk(self.item)

        return self

    def set(self, text=None, comments_disabled=None, likes_disabled=None, sharing_disabled=None,
            verification_hidden=None):
        args = [text, comments_disabled, likes_disabled, sharing_disabled, verification_hidden]
        if all(v is None for v in args):
            raise exceptions.PostException('Empty edit requested')

        post_media = list(self.media_manager.dynamo.generate_by_post(self.id))
        if text == '' and not post_media:
            raise exceptions.PostException('Cannot set text to null on text-only post')

        text_tags = self.user_manager.get_text_tags(text) if text is not None else None
        self.item = self.dynamo.set(
            self.id, text=text, text_tags=text_tags, comments_disabled=comments_disabled,
            likes_disabled=likes_disabled, sharing_disabled=sharing_disabled,
            verification_hidden=verification_hidden,
        )
        self.item['mediaObjects'] = post_media
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
