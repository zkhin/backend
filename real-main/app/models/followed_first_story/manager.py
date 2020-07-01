import logging

from app import models
from app.models.follower.enums import FollowStatus

from .dynamo import FollowedFirstStoryDynamo

logger = logging.getLogger()


class FollowedFirstStoryManager:
    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['followed_first_story'] = self
        self.follower_manager = managers.get('follower') or models.FollowerManager(clients, managers=managers)
        self.post_manager = managers.get('post') or models.PostManager(clients, managers=managers)
        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = FollowedFirstStoryDynamo(clients['dynamo'])

    def refresh_after_story_change(self, story_prev=None, story_now=None):
        "Refresh the followedFirstStory items, if needed, after the a story has changed."
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

        follower_user_ids_generator = self.follower_manager.generate_follower_user_ids(
            user_id, follow_status=FollowStatus.FOLLOWING,
        )
        if ffs_prev and not ffs_now:
            # a story was deleted, and there are no more stories to take its place as ffs
            self.dynamo.delete_all(follower_user_ids_generator, user_id)

        if not ffs_prev and ffs_now:
            # there was no ffs, but a story was added and can now be ffs
            self.dynamo.set_all(follower_user_ids_generator, ffs_now)

        if ffs_prev and ffs_now:
            if ffs_prev != ffs_now:
                # the ffs has changed: either different post, or same post but that post changed
                self.dynamo.set_all(follower_user_ids_generator, ffs_now)

        if not ffs_prev and not ffs_now:
            assert False, 'Should be unreachable condition'
