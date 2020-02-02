import logging
import os

from app.models.album.dynamo import AlbumDynamo
from app.models.media.dynamo import MediaDynamo
from app.models.media.enums import MediaType, MediaStatus
from app.models.user.dynamo import UserDynamo

from . import enums, exceptions
from .dynamo import PostDynamo
from .enums import FlagStatus, PostStatus

logger = logging.getLogger()

# number of times a post must get flagged before an alert is fired
FLAGGED_ALERT_THRESHOLD = int(os.environ.get('FLAGGED_ALERT_THRESHOLD', 1))


class Post:

    enums = enums
    exceptions = exceptions
    FlagStatus = FlagStatus

    def __init__(self, item, clients, trending_manager=None, feed_manager=None, followed_first_story_manager=None,
                 like_manager=None, media_manager=None, post_view_manager=None, user_manager=None,
                 comment_manager=None, flagged_alert_threshold=FLAGGED_ALERT_THRESHOLD):
        self.flagged_alert_threshold = flagged_alert_threshold

        if 'dynamo' in clients:
            self.dynamo = PostDynamo(clients['dynamo'])
            self.album_dynamo = AlbumDynamo(clients['dynamo'])
            self.media_dynamo = MediaDynamo(clients['dynamo'])
            self.user_dynamo = UserDynamo(clients['dynamo'])

        if comment_manager:
            self.comment_manager = comment_manager
        if feed_manager:
            self.feed_manager = feed_manager
        if followed_first_story_manager:
            self.followed_first_story_manager = followed_first_story_manager
        if like_manager:
            self.like_manager = like_manager
        if media_manager:
            self.media_manager = media_manager
        if post_view_manager:
            self.post_view_manager = post_view_manager
        if trending_manager:
            self.trending_manager = trending_manager
        if user_manager:
            self.user_manager = user_manager

        self.item = item
        self.id = item['postId']
        self.posted_by_user_id = item['postedByUserId']

    @property
    def post_status(self):
        return self.item['postStatus']

    def refresh_item(self, strongly_consistent=False):
        self.item = self.dynamo.get_post(self.id, strongly_consistent=strongly_consistent)
        return self

    def serialize(self, caller_user_id):
        resp = self.item.copy()
        user = self.user_manager.get_user(self.posted_by_user_id)
        resp['postedBy'] = user.serialize(caller_user_id)
        return resp

    def complete(self):
        "Transition the post to COMPLETED status"
        if self.post_status in (PostStatus.COMPLETED, PostStatus.ARCHIVED, PostStatus.DELETING):
            msg = f'Refusing to change post `{self.id}` with status `{self.post_status}` to `{PostStatus.COMPLETED}`'
            raise exceptions.PostException(msg)

        # Determine the original_post_id, if this post isn't original
        # Note that in order to simplify the problem and focus on the use case that matters,
        # we declare that only posts with exactly one media item of type IMAGE may be non-original.
        # That is to say, text-only posts or multiple-media posts will never have originalPostId set.
        original_post_id = None
        media_items = list(self.media_dynamo.generate_by_post(self.id))
        media_item = media_items[0] if media_items else None
        if media_item and media_item['mediaType'] == MediaType.IMAGE:
            first_media_id = self.media_dynamo.get_first_media_id_with_checksum(media_item['checksum'])
            if first_media_id and first_media_id != media_item['mediaId']:
                first_media_item = self.media_dynamo.get_media(first_media_id)
                original_post_id = first_media_item['postId'] if first_media_item else None

        # complete the post
        transacts = [
            self.dynamo.transact_set_post_status(self.item, PostStatus.COMPLETED, original_post_id=original_post_id),
            self.user_dynamo.transact_increment_post_count(self.posted_by_user_id),
        ]
        if album_id := self.item.get('albumId'):
            transacts.append(self.album_dynamo.transact_add_post(album_id))

        self.dynamo.client.transact_write_items(transacts)
        self.item = self.dynamo.get_post(self.id, strongly_consistent=True)

        # update the first story if needed
        if self.item.get('expiresAt'):
            self.followed_first_story_manager.refresh_after_story_change(story_now=self.item)

        # add post to feeds
        self.feed_manager.add_post_to_followers_feeds(self.posted_by_user_id, self.item)
        return self

    def archive(self):
        "Transition the post to ARCHIVED status"
        if self.post_status in (PostStatus.ARCHIVED, PostStatus.DELETING):
            msg = f'Refusing to change post `{self.id}` with status `{self.post_status}` to `{PostStatus.ARCHIVED}`'
            raise exceptions.PostException(msg)

        # archive the post and its media objects
        self.item['mediaObjects'] = []
        transacts = [self.dynamo.transact_set_post_status(self.item, PostStatus.ARCHIVED)]
        if self.post_status == PostStatus.COMPLETED:
            transacts.append(self.user_dynamo.transact_decrement_post_count(self.posted_by_user_id))
            if album_id := self.item.get('albumId'):
                transacts.append(self.album_dynamo.transact_remove_post(album_id))

        for media_item in self.media_dynamo.generate_by_post(self.id):
            transacts.append(self.media_dynamo.transact_set_status(media_item, MediaStatus.ARCHIVED))
            self.item['mediaObjects'].append(media_item)

        self.dynamo.client.transact_write_items(transacts)

        # update in-memory copy of dynamo state, don't worry about the gsi's that were updated
        prev_post_status = self.post_status
        self.item['postStatus'] = PostStatus.ARCHIVED
        for media_item in self.item['mediaObjects']:
            media_item['mediaStatus'] = MediaStatus.ARCHIVED

        # dislike all likes of the post
        self.like_manager.dislike_all_of_post(self.id)

        # if it was the first followed story, refresh that
        if self.item.get('expiresAt'):
            self.followed_first_story_manager.refresh_after_story_change(story_prev=self.item)

        # update feeds if needed
        if prev_post_status == PostStatus.COMPLETED:
            self.feed_manager.delete_post_from_followers_feeds(self.posted_by_user_id, self.id)
        return self

    def restore(self):
        "Transition the post out of ARCHIVED status"
        if self.post_status != PostStatus.ARCHIVED:
            msg = f'Post `{self.id}` is not archived (has status `{self.post_status}`)'
            raise exceptions.PostException(msg)

        # first determine what our target statuses are
        post_status = PostStatus.COMPLETED
        media_statuses = []
        media_items = []
        for media_item in self.media_dynamo.generate_by_post(self.id):
            media = self.media_manager.init_media(media_item)
            media_status = (
                MediaStatus.UPLOADED if media.has_all_s3_objects()
                else MediaStatus.AWAITING_UPLOAD
            )
            media_statuses.append(media_status)
            media_items.append(media.item)
            if media_status != MediaStatus.UPLOADED:
                post_status = PostStatus.PENDING

        # restore the post
        transacts = [self.dynamo.transact_set_post_status(self.item, post_status)]
        if post_status == PostStatus.COMPLETED:
            transacts.append(self.user_dynamo.transact_increment_post_count(self.posted_by_user_id))
            if album_id := self.item.get('albumId'):
                transacts.append(self.album_dynamo.transact_add_post(album_id))

        for media_item, media_status in zip(media_items, media_statuses):
            transacts.append(self.media_dynamo.transact_set_status(media_item, media_status))

        self.dynamo.client.transact_write_items(transacts)

        # update in-memory copy of dynamo state
        self.refresh_item(strongly_consistent=True)
        self.item['mediaObjects'] = [
            self.media_dynamo.get_media(media_item['mediaId'], strongly_consistent=True)
            for media_item in media_items
        ]

        if post_status == PostStatus.COMPLETED:
            # refresh the first story if needed
            if self.item.get('expiresAt'):
                self.followed_first_story_manager.refresh_after_story_change(story_now=self.item)
            # update feeds
            self.feed_manager.add_post_to_followers_feeds(self.posted_by_user_id, self.item)

        return self

    def delete(self):
        "Delete the post and all its media"
        # marke the post and the media as in the deleting process
        self.item['mediaObjects'] = []
        transacts = [self.dynamo.transact_set_post_status(self.item, PostStatus.DELETING)]
        if self.post_status == PostStatus.COMPLETED:
            transacts.append(self.user_dynamo.transact_decrement_post_count(self.posted_by_user_id))
            if album_id := self.item.get('albumId'):
                transacts.append(self.album_dynamo.transact_remove_post(album_id))

        for media_item in self.media_dynamo.generate_by_post(self.id):
            transacts.append(self.media_dynamo.transact_set_status(media_item, MediaStatus.DELETING))
            self.item['mediaObjects'].append(media_item)

        self.dynamo.client.transact_write_items(transacts)

        # update in-memory copy of dynamo state, don't worry about the gsi's that were updated
        prev_post_status = self.post_status
        self.item['postStatus'] = PostStatus.DELETING
        for media_item in self.item['mediaObjects']:
            media_item['mediaStatus'] = MediaStatus.DELETING

        # dislike all likes of the post
        self.like_manager.dislike_all_of_post(self.id)

        # delete all comments on the post
        self.comment_manager.delete_all_on_post(self.id)

        # unflag all flags of the post
        for flag_item in self.dynamo.generate_flag_items_by_post(self.id):
            self.unflag(flag_item['flaggerUserId'])

        # if it was the first followed story, refresh that
        if self.item.get('expiresAt'):
            self.followed_first_story_manager.refresh_after_story_change(story_prev=self.item)

        # remove it from feeds, user post count
        if prev_post_status == PostStatus.COMPLETED:
            self.feed_manager.delete_post_from_followers_feeds(self.posted_by_user_id, self.id)

        # delete any post views of it
        self.post_view_manager.delete_all_for_post(self.id)

        # delete the trending index, if it exists
        self.trending_manager.dynamo.delete_trending(self.id)

        # do the deletes for real
        for media_item in self.item['mediaObjects']:
            media = self.media_manager.init_media(media_item)
            media.delete_all_s3_objects()
            self.dynamo.client.delete_item_by_pk(media.item)
        self.dynamo.client.delete_item_by_pk(self.item)

        return self

    def flag(self, user_id):
        flag_count = self.item.get('flagCount', 0)
        self.dynamo.add_flag_and_increment_flag_count(self.id, user_id)
        self.item['flagCount'] = flag_count + 1

        # raise an alert if needed, piggy backing on error alerting for now
        if self.item['flagCount'] >= self.flagged_alert_threshold:
            logger.warning(f'FLAGGED: Post `{self.id}` has been flagged `{self.item["flagCount"]}` time(s).')

        return self

    def unflag(self, user_id):
        flag_count = self.item.get('flagCount', 0)
        self.dynamo.delete_flag_and_decrement_flag_count(self.id, user_id)
        self.item['flagCount'] = flag_count - 1
        return self

    def set(self, text=None, comments_disabled=None, likes_disabled=None, sharing_disabled=None,
            verification_hidden=None):
        args = [text, comments_disabled, likes_disabled, sharing_disabled, verification_hidden]
        if all(v is None for v in args):
            raise exceptions.PostException('Empty edit requested')

        post_media = list(self.media_dynamo.generate_by_post(self.id))
        if text == '' and not post_media:
            raise exceptions.PostException('Cannot set text to null on text-only post')

        text_tags = self.user_manager.get_text_tags(text) if text is not None else None
        self.item = self.dynamo.set(
            self.id, text=text, text_tags=text_tags, comments_disabled=comments_disabled,
            likes_disabled=likes_disabled, sharing_disabled=sharing_disabled, verification_hidden=verification_hidden,
        )
        self.item['mediaObjects'] = post_media
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
        if album_id:
            album_item = self.album_dynamo.get_album(album_id)
            if not album_item:
                raise exceptions.PostException(f'Album `{album_id}` does not exist')
            if album_item['ownedByUserId'] != self.posted_by_user_id:
                msg = f'Album `{album_id}` and post `{self.id}` belong to different users'
                raise exceptions.PostException(msg)

        transacts = [self.dynamo.transact_set_album_id(self.item, album_id)]
        if self.item['postStatus'] == PostStatus.COMPLETED:
            if prev_album_id:
                transacts.append(self.album_dynamo.transact_remove_post(prev_album_id))
            if album_id:
                transacts.append(self.album_dynamo.transact_add_post(album_id))

        self.dynamo.client.transact_write_items(transacts)
        self.refresh_item(strongly_consistent=True)
        return self
