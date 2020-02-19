import logging

import pendulum

from app.models.media.enums import MediaStatus

from . import enums, exceptions
from .enums import FlagStatus, PostStatus

logger = logging.getLogger()


class Post:

    enums = enums
    exceptions = exceptions
    FlagStatus = FlagStatus

    def __init__(self, item, post_dynamo, post_manager=None, trending_manager=None, feed_manager=None,
                 like_manager=None, media_manager=None, post_view_manager=None, user_manager=None,
                 comment_manager=None, flag_manager=None, album_manager=None, followed_first_story_manager=None):
        self.dynamo = post_dynamo

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

    def complete(self, now=None):
        "Transition the post to COMPLETED status"
        now = now or pendulum.now('utc')

        if self.post_status in (PostStatus.COMPLETED, PostStatus.ARCHIVED, PostStatus.DELETING):
            msg = f'Refusing to change post `{self.id}` with status `{self.post_status}` to `{PostStatus.COMPLETED}`'
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
            self.user_manager.dynamo.transact_increment_post_count(self.posted_by_user_id),
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
        self.feed_manager.add_post_to_followers_feeds(self.posted_by_user_id, self.item)

        # update album art if needed
        if album:
            album.update_art_if_needed()

        return self

    def archive(self):
        "Transition the post to ARCHIVED status"
        if self.post_status in (PostStatus.ARCHIVED, PostStatus.DELETING):
            msg = f'Refusing to change post `{self.id}` with status `{self.post_status}` to `{PostStatus.ARCHIVED}`'
            raise exceptions.PostException(msg)

        # we only have to operate on the album if the previous status was COMPLETED
        album = None
        if self.post_status == PostStatus.COMPLETED:
            if album_id := self.item.get('albumId'):
                album = self.album_manager.get_album(album_id)

        # archive the post and its media objects
        transacts = [self.dynamo.transact_set_post_status(self.item, PostStatus.ARCHIVED)]
        if self.post_status == PostStatus.COMPLETED:
            transacts.append(self.user_manager.dynamo.transact_decrement_post_count(self.posted_by_user_id))
            if album:
                transacts.append(album.dynamo.transact_remove_post(album.id))

        media_items = []
        for media_item in self.media_manager.dynamo.generate_by_post(self.id):
            transacts.append(self.media_manager.dynamo.transact_set_status(media_item, MediaStatus.ARCHIVED))
            media_items.append(media_item)

        self.dynamo.client.transact_write_items(transacts)

        # update in-memory copy of dynamo state
        prev_post_status = self.post_status
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

        # update feeds if needed
        if prev_post_status == PostStatus.COMPLETED:
            self.feed_manager.delete_post_from_followers_feeds(self.posted_by_user_id, self.id)

        # update album art if needed
        if album:
            album.update_art_if_needed()

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
        for media_item in self.media_manager.dynamo.generate_by_post(self.id):
            media = self.media_manager.init_media(media_item)
            media_status = (
                MediaStatus.UPLOADED if media.has_all_s3_objects()
                else MediaStatus.AWAITING_UPLOAD
            )
            media_statuses.append(media_status)
            media_items.append(media.item)
            if media_status != MediaStatus.UPLOADED:
                post_status = PostStatus.PENDING

        # we only need the album if the new post status is COMPLETED
        album, album_rank = None, None
        if post_status == PostStatus.COMPLETED:
            if album_id := self.item.get('albumId'):
                album = self.album_manager.get_album(album_id)
                album_rank = album.get_next_last_rank()

        # restore the post
        transacts = [self.dynamo.transact_set_post_status(self.item, post_status, album_rank=album_rank)]

        if post_status == PostStatus.COMPLETED:
            transacts.append(self.user_manager.dynamo.transact_increment_post_count(self.posted_by_user_id))
            if album:
                old_rank_count = album.item.get('rankCount')
                transacts.append(self.album_manager.dynamo.transact_add_post(album.id, old_rank_count=old_rank_count))

        for media_item, media_status in zip(media_items, media_statuses):
            transacts.append(self.media_manager.dynamo.transact_set_status(media_item, media_status))

        self.dynamo.client.transact_write_items(transacts)

        # update in-memory copy of dynamo state
        self.refresh_item(strongly_consistent=True)
        self.item['mediaObjects'] = [
            self.media_manager.dynamo.get_media(media_item['mediaId'], strongly_consistent=True)
            for media_item in media_items
        ]

        if post_status == PostStatus.COMPLETED:
            # refresh the first story if needed
            if self.item.get('expiresAt'):
                self.followed_first_story_manager.refresh_after_story_change(story_now=self.item)
            # update feeds
            self.feed_manager.add_post_to_followers_feeds(self.posted_by_user_id, self.item)
            # update album art if needed
            if album:
                album.update_art_if_needed()

        return self

    def delete(self):
        "Delete the post and all its media"

        # we only have to the album if the previous status was COMPLETED
        album = None
        if self.post_status == PostStatus.COMPLETED:
            if album_id := self.item.get('albumId'):
                album = self.album_manager.get_album(album_id)

        # mark the post and the media as in the deleting process
        media_items = []
        transacts = [self.dynamo.transact_set_post_status(self.item, PostStatus.DELETING)]
        if self.post_status == PostStatus.COMPLETED:
            transacts.append(self.user_manager.dynamo.transact_decrement_post_count(self.posted_by_user_id))
            if album:
                transacts.append(album.dynamo.transact_remove_post(album.id))

        for media_item in self.media_manager.dynamo.generate_by_post(self.id):
            transacts.append(self.media_manager.dynamo.transact_set_status(media_item, MediaStatus.DELETING))
            media_items.append(media_item)

        self.dynamo.client.transact_write_items(transacts)

        # update in-memory copy of dynamo state
        prev_post_status = self.post_status
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
            self.feed_manager.delete_post_from_followers_feeds(self.posted_by_user_id, self.id)

        # delete any post views of it
        self.post_view_manager.delete_all_for_post(self.id)

        # delete the trending index, if it exists
        self.trending_manager.dynamo.delete_trending(self.id)

        # update album art, if needed
        if album:
            album.update_art_if_needed()

        # do the deletes for real
        for media_item in self.item['mediaObjects']:
            media = self.media_manager.init_media(media_item)
            media.delete_all_s3_objects()
            self.dynamo.client.delete_item_by_pk(media.item)
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
        album = self.album_manager.get_album(album_id) if album_id else None
        album_rank = album.get_next_last_rank() if album and self.item['postStatus'] == PostStatus.COMPLETED else None
        if album_id:
            if not album:
                raise exceptions.PostException(f'Album `{album_id}` does not exist')
            if album.item['ownedByUserId'] != self.posted_by_user_id:
                msg = f'Album `{album_id}` and post `{self.id}` belong to different users'
                raise exceptions.PostException(msg)
            post_media = list(self.media_manager.dynamo.generate_by_post(self.id))
            if not post_media:
                raise exceptions.PostException('Text-only posts may not be placed in albums')

        transacts = [self.dynamo.transact_set_album_id(self.item, album_id, album_rank=album_rank)]
        if self.item['postStatus'] == PostStatus.COMPLETED:
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

            if preceding_post.item['postedByUserId'] != self.item['postedByUserId']:
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
