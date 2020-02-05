import itertools
import logging

import pendulum

from app.models import comment, feed, flag, followed_first_story, like, media, post_view, trending, user
from app.models.album.dynamo import AlbumDynamo
from app.models.media.dynamo import MediaDynamo
from app.models.user.dynamo import UserDynamo

from . import enums, exceptions
from .dynamo import PostDynamo
from .model import Post

logger = logging.getLogger()


class PostManager:

    enums = enums
    exceptions = exceptions

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['post'] = self
        self.comment_manager = managers.get('comment') or comment.CommentManager(clients, managers=managers)
        self.feed_manager = managers.get('feed') or feed.FeedManager(clients, managers=managers)
        self.flag_manager = managers.get('flag') or flag.FlagManager(clients, managers=managers)
        self.followed_first_story_manager = (
            managers.get('followed_first_story')
            or followed_first_story.FollowedFirstStoryManager(clients, managers=managers)
        )
        self.like_manager = managers.get('like') or like.LikeManager(clients, managers=managers)
        self.media_manager = managers.get('media') or media.MediaManager(clients, managers=managers)
        self.post_view_manager = managers.get('post_view') or post_view.PostViewManager(clients, managers=managers)
        self.trending_manager = managers.get('trending') or trending.TrendingManager(clients, managers=managers)
        self.user_manager = managers.get('user') or user.UserManager(clients, managers=managers)

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = PostDynamo(clients['dynamo'])
            self.album_dynamo = AlbumDynamo(clients['dynamo'])
            self.media_dynamo = MediaDynamo(clients['dynamo'])
            self.user_dynamo = UserDynamo(clients['dynamo'])

    def get_post(self, post_id):
        post_item = self.dynamo.get_post(post_id)
        return self.init_post(post_item) if post_item else None

    def init_post(self, post_item):
        kwargs = {
            'comment_manager': self.comment_manager,
            'feed_manager': self.feed_manager,
            'flag_manager': self.flag_manager,
            'followed_first_story_manager': self.followed_first_story_manager,
            'like_manager': self.like_manager,
            'media_manager': self.media_manager,
            'post_view_manager': self.post_view_manager,
            'trending_manager': self.trending_manager,
            'user_manager': self.user_manager,
        }
        return Post(post_item, self.clients, **kwargs) if post_item else None

    def add_post(self, posted_by_user_id, post_id, media_uploads=[], text=None, lifetime_duration=None, album_id=None,
                 comments_disabled=None, likes_disabled=None, sharing_disabled=None, verification_hidden=None,
                 now=None):
        now = now or pendulum.now('utc')

        if not text and not media_uploads:
            msg = f'Refusing to add post `{post_id}` for user `{posted_by_user_id}` without text or media'
            raise exceptions.PostException(msg)

        expires_at = now + lifetime_duration if lifetime_duration is not None else None
        if expires_at and expires_at <= now:
            msg = f'Refusing to add post `{post_id}` for user `{posted_by_user_id}` with negative lifetime'
            raise exceptions.PostException(msg)

        text_tags = self.user_manager.get_text_tags(text) if text is not None else None

        # if an album is specified, verify it exists and is ours
        if album_id:
            album_item = self.album_dynamo.get_album(album_id)
            if not album_item:
                raise exceptions.PostException(f'Album `{album_id}` does not exist')
            if album_item['ownedByUserId'] != posted_by_user_id:
                msg = f'Album `{album_id}` does not not belong to caller user `{posted_by_user_id}`'
                raise exceptions.PostException(msg)

        # add the pending post & media to dynamo in a transaction
        transacts = [self.dynamo.transact_add_pending_post(
            posted_by_user_id, post_id, posted_at=now, expires_at=expires_at, text=text, text_tags=text_tags,
            comments_disabled=comments_disabled, likes_disabled=likes_disabled, sharing_disabled=sharing_disabled,
            verification_hidden=verification_hidden, album_id=album_id,
        )]
        for mu in media_uploads:
            # 'media_upload' is straight from graphql, format dictated by schema
            transacts.append(self.media_dynamo.transact_add_media(
                posted_by_user_id, post_id, mu['mediaId'], mu['mediaType'], posted_at=now,
                taken_in_real=mu.get('takenInReal'), original_format=mu.get('originalFormat'),
            ))
        self.dynamo.client.transact_write_items(transacts)

        post_item = self.dynamo.get_post(post_id, strongly_consistent=True)
        post = self.init_post(post_item)

        # text-only posts are completed immmediately
        if not media_uploads:
            post.complete()

        post.item['mediaObjects'] = [
            self.media_dynamo.get_media(mu['mediaId'], strongly_consistent=True)
            for mu in media_uploads
        ]
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
            user_item = self.user_dynamo.get_user(post_item['postedByUserId'])
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
