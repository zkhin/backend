import logging

from app.models import follow, like

from . import enums, exceptions
from .dynamo import BlockDynamo

logger = logging.getLogger()


class BlockManager:

    enums = enums
    exceptions = exceptions

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['block'] = self
        self.follow_manager = managers.get('follow') or follow.FollowManager(clients, managers=managers)
        self.like_manager = managers.get('like') or like.LikeManager(clients, managers=managers)

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = BlockDynamo(clients['dynamo'])

    def is_blocked(self, blocker_user_id, blocked_user_id):
        block_item = self.dynamo.get_block(blocker_user_id, blocked_user_id)
        return bool(block_item)

    def get_block_status(self, blocker_user_id, blocked_user_id):
        if blocker_user_id == blocked_user_id:
            return enums.BlockStatus.SELF
        block_item = self.dynamo.get_block(blocker_user_id, blocked_user_id)
        return enums.BlockStatus.BLOCKING if block_item else enums.BlockStatus.NOT_BLOCKING

    def block(self, blocker_user, blocked_user):
        block_item = self.dynamo.add_block(blocker_user.id, blocked_user.id)

        # force-unfollow them if we're following them
        try:
            self.follow_manager.unfollow(blocker_user.id, blocked_user.id, force=True)
        except self.follow_manager.exceptions.FollowException:
            pass

        # force-unfollow us if they're following us
        try:
            self.follow_manager.unfollow(blocked_user.id, blocker_user.id, force=True)
        except self.follow_manager.exceptions.FollowException:
            pass

        # force-dislike any likes of posts between the two of us
        self.like_manager.dislike_all_by_user_from_user(blocker_user.id, blocked_user.id)
        self.like_manager.dislike_all_by_user_from_user(blocked_user.id, blocker_user.id)

        return block_item

    def unblock(self, blocker_user, blocked_user):
        return self.dynamo.delete_block(blocker_user.id, blocked_user.id)

    def unblock_all_blocks(self, user_id):
        """
        Unblock everyone who the user has blocked, or has blocked the user.
        Intended to be called with admin-level authentication (not authenticated as the user themselves).
        """
        self.dynamo.delete_all_blocks_by_user(user_id)
        self.dynamo.delete_all_blocks_of_user(user_id)
