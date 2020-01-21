import logging

from app.models import post

from . import enums, exceptions
from .dynamo import LikeDynamo

logger = logging.getLogger()


class Like:

    enums = enums
    exceptions = exceptions

    def __init__(self, like_item, clients):
        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = LikeDynamo(clients['dynamo'])
            self.post_dynamo = post.dynamo.PostDynamo(clients['dynamo'])
        self.item = like_item
        self.liked_by_user_id = like_item['likedByUserId']
        self.post_id = like_item['postId']

    def dislike(self):
        like_status = self.item['likeStatus']
        transacts = [
            self.dynamo.transact_delete_like(self.liked_by_user_id, self.post_id, like_status),
            self.post_dynamo.transact_decrement_like_count(self.post_id, like_status),
        ]
        exceptions = [
            self.exceptions.NotLikedWithStatus(self.liked_by_user_id, self.post_id, like_status),
            post.exceptions.UnableToDecrementPostLikeCounter(self.post_id),
        ]
        self.dynamo.client.transact_write_items(transacts, exceptions)
