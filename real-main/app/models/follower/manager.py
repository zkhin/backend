import logging

from app import models
from app.models.user.enums import UserPrivacyStatus

from .dynamo.base import FollowerDynamo
from .dynamo.first_story import FirstStoryDynamo
from .enums import FollowStatus
from .exceptions import FollowerAlreadyExists, FollowerException
from .model import Follower
from .postprocessor import FollowerPostProcessor

logger = logging.getLogger()


class FollowerManager:
    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['follower'] = self
        self.feed_manager = managers.get('feed') or models.FeedManager(clients, managers=managers)
        self.block_manager = managers.get('block') or models.BlockManager(clients, managers=managers)
        self.like_manager = managers.get('like') or models.LikeManager(clients, managers=managers)
        self.post_manager = managers.get('post') or models.PostManager(clients, managers=managers)
        self.user_manager = managers.get('user') or models.UserManager(clients, managers=managers)

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = FollowerDynamo(clients['dynamo'])
            self.first_story_dynamo = FirstStoryDynamo(clients['dynamo'])

    @property
    def postprocessor(self):
        if not hasattr(self, '_postprocessor'):
            self._postprocessor = FollowerPostProcessor(user_manager=self.user_manager)
        return self._postprocessor

    def get_follow(self, follower_user_id, followed_user_id, strongly_consistent=False):
        item = self.dynamo.get_following(
            follower_user_id, followed_user_id, strongly_consistent=strongly_consistent
        )
        return self.init_follow(item) if item else None

    def init_follow(self, follow_item):
        return Follower(
            follow_item,
            self.dynamo,
            self.first_story_dynamo,
            feed_manager=self.feed_manager,
            like_manager=self.like_manager,
            post_manager=self.post_manager,
            user_manager=self.user_manager,
        )

    def get_follow_status(self, follower_user_id, followed_user_id):
        if follower_user_id == followed_user_id:
            return FollowStatus.SELF
        follow = self.get_follow(follower_user_id, followed_user_id)
        if not follow:
            return FollowStatus.NOT_FOLLOWING
        return follow.status

    def generate_follower_user_ids(self, followed_user_id, follow_status=None):
        "Return a generator that produces user ids of users that follow the given user"
        gen = self.dynamo.generate_follower_items(followed_user_id, follow_status=follow_status)
        gen = map(lambda item: item['followerUserId'], gen)
        return gen

    def generate_followed_user_ids(self, follower_user_id, follow_status=None):
        "Return a generator that produces user ids of users given user follows"
        gen = self.dynamo.generate_followed_items(follower_user_id, follow_status=follow_status)
        gen = map(lambda item: item['followedUserId'], gen)
        return gen

    def request_to_follow(self, follower_user, followed_user):
        "Returns the status of the follow request"
        if self.get_follow(follower_user.id, followed_user.id):
            raise FollowerAlreadyExists(follower_user.id, followed_user.id)

        # can't follow a user that has blocked us
        if self.block_manager.is_blocked(followed_user.id, follower_user.id):
            raise FollowerException(f'User has been blocked by user `{followed_user.id}`')

        # can't follow a user we have blocked
        if self.block_manager.is_blocked(follower_user.id, followed_user.id):
            raise FollowerException(f'User has blocked user `{followed_user.id}`')

        follow_status = (
            FollowStatus.REQUESTED
            if followed_user.item['privacyStatus'] == UserPrivacyStatus.PRIVATE
            else FollowStatus.FOLLOWING
        )
        follow_item = self.dynamo.add_following(follower_user.id, followed_user.id, follow_status)

        if follow_status == FollowStatus.FOLLOWING:
            # async with dynamo stream handler?
            self.feed_manager.add_users_posts_to_feed(follower_user.id, followed_user.id)
            post = self.post_manager.dynamo.get_next_completed_post_to_expire(followed_user.id)
            if post:
                self.first_story_dynamo.set_all([follower_user.id], post)

        return self.init_follow(follow_item)

    def accept_all_requested_follow_requests(self, followed_user_id):
        for item in self.dynamo.generate_follower_items(followed_user_id, FollowStatus.REQUESTED):
            # can't batch this: dynamo doesn't support batch updates
            self.init_follow(item).accept()

    def delete_all_denied_follow_requests(self, followed_user_id):
        for item in self.dynamo.generate_follower_items(followed_user_id, FollowStatus.DENIED):
            # TODO: do as batch write
            self.dynamo.delete_following(item)

    def reset_follower_items(self, followed_user_id):
        for item in self.dynamo.generate_follower_items(followed_user_id):
            # they were following us, then do an unfollow() to keep their counts correct
            if item['followStatus'] == FollowStatus.FOLLOWING:
                self.init_follow(item).unfollow()
            else:
                # TODO: do as batch write
                self.dynamo.delete_following(item)

    def reset_followed_items(self, follower_user_id):
        for item in self.dynamo.generate_followed_items(follower_user_id):
            # if we were following them, then do an unfollow() to keep their counts correct
            if item['followStatus'] == FollowStatus.FOLLOWING:
                self.init_follow(item).unfollow()
            else:
                # TODO: do as batch write
                self.dynamo.delete_following(item)

    def refresh_first_story(self, story_prev=None, story_now=None):
        "Refresh the firstStory items, if needed, after the a story has changed."
        assert story_prev or story_now
        if story_prev:
            assert 'expiresAt' in story_prev
        if story_now:
            assert 'expiresAt' in story_now
        if story_prev and story_now:
            assert story_prev['postId'] == story_now['postId']
        post_id = story_prev['postId'] if story_prev else story_now['postId']
        user_id = story_prev['postedByUserId'] if story_prev else story_now['postedByUserId']

        # dynamo query ordering not guaranteed,
        # so to make sure things are consistent we exclude the post we just operated on from this query
        db_story = self.post_manager.dynamo.get_next_completed_post_to_expire(user_id, exclude_post_id=post_id)

        # figgure out what the followed first story was prev, and is now, the operation we're refreshing for
        ffs_prev = next(
            iter(sorted(filter(lambda s: s is not None, [db_story, story_prev]), key=lambda s: s['expiresAt'])),
            None,
        )
        ffs_now = next(
            iter(sorted(filter(lambda s: s is not None, [db_story, story_now]), key=lambda s: s['expiresAt'])),
            None,
        )

        follower_uids_generator = self.generate_follower_user_ids(user_id, follow_status=FollowStatus.FOLLOWING)
        if ffs_prev and not ffs_now:
            # a story was deleted, and there are no more stories to take its place as ffs
            self.first_story_dynamo.delete_all(follower_uids_generator, user_id)

        if not ffs_prev and ffs_now:
            # there was no ffs, but a story was added and can now be ffs
            self.first_story_dynamo.set_all(follower_uids_generator, ffs_now)

        if ffs_prev and ffs_now:
            if ffs_prev != ffs_now:
                # the ffs has changed: either different post, or same post but that post changed
                self.first_story_dynamo.set_all(follower_uids_generator, ffs_now)

        if not ffs_prev and not ffs_now:
            raise AssertionError('Should be unreachable condition')
