import logging

from app.models import post

from . import enums, exceptions

logger = logging.getLogger()


class Like:

    enums = enums
    exceptions = exceptions

    def __init__(self, like_item, like_dynamo, post_manager=None):
        self.dynamo = like_dynamo
        if post_manager:
            self.post_manager = post_manager
        self.item = like_item
        self.liked_by_user_id = like_item['likedByUserId']
        self.post_id = like_item['postId']

    def dislike(self):
        like_status = self.item['likeStatus']
        transacts = [
            self.dynamo.transact_delete_like(self.liked_by_user_id, self.post_id, like_status),
            self.post_manager.dynamo.transact_decrement_like_count(self.post_id, like_status),
        ]
        exceptions = [
            self.exceptions.NotLikedWithStatus(self.liked_by_user_id, self.post_id, like_status),
            post.exceptions.UnableToDecrementPostLikeCounter(self.post_id),
        ]
        self.dynamo.client.transact_write_items(transacts, exceptions)
