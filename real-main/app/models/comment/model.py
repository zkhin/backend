import logging

from . import exceptions

logger = logging.getLogger()


class Comment:

    exceptions = exceptions

    def __init__(self, comment_item, comment_dynamo, post_manager=None, user_manager=None):
        self.dynamo = comment_dynamo
        self.post_manager = post_manager
        self.user_manager = user_manager
        self.id = comment_item['commentId']
        self.item = comment_item

    def serialize(self, caller_user_id):
        resp = self.item.copy()
        user = self.user_manager.get_user(resp['userId'])
        resp['commentedBy'] = user.serialize(caller_user_id)
        return resp

    def delete(self):
        # order matters to moto (in test suite), but not on dynamo
        transacts = [
            self.post_manager.dynamo.transact_decrement_comment_count(self.item['postId']),
            self.dynamo.transact_delete_comment(self.id),
        ]
        self.dynamo.client.transact_write_items(transacts)
        return self
