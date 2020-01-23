import logging

from app.models import post

from . import exceptions
from .dynamo import CommentDynamo

logger = logging.getLogger()


class Comment:

    exceptions = exceptions

    def __init__(self, comment_item, clients, user_manager=None):
        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = CommentDynamo(clients['dynamo'])
            self.post_dynamo = post.dynamo.PostDynamo(clients['dynamo'])
        self.user_manager = user_manager
        self.id = comment_item['commentId']
        self.item = comment_item

    def serialize(self):
        resp = self.item.copy()
        user = self.user_manager.get_user(resp['userId'])
        resp['commentedBy'] = user.serialize()
        return resp

    def delete(self):
        # order matters to moto (in test suite), but not on dynamo
        transacts = [
            self.post_dynamo.transact_decrement_comment_count(self.item['postId']),
            self.dynamo.transact_delete_comment(self.id),
        ]
        self.dynamo.client.transact_write_items(transacts)
        return self
