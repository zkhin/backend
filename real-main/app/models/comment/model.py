import logging

from . import exceptions

logger = logging.getLogger()


class Comment:

    exceptions = exceptions

    def __init__(self, comment_item, comment_dynamo, post_manager=None, user_manager=None, view_manager=None):
        self.dynamo = comment_dynamo
        self.post_manager = post_manager
        self.user_manager = user_manager
        self.view_manager = view_manager
        self.item = comment_item
        self.id = comment_item['commentId']
        self.user_id = comment_item['userId']
        self.post_id = comment_item['postId']

    def serialize(self, caller_user_id):
        resp = self.item.copy()
        user = self.user_manager.get_user(self.user_id)
        resp['commentedBy'] = user.serialize(caller_user_id)
        resp['viewedStatus'] = self.view_manager.get_viewed_status(self, caller_user_id)
        return resp

    def delete(self):
        # order matters to moto (in test suite), but not on dynamo
        transacts = [
            self.post_manager.dynamo.transact_decrement_comment_count(self.post_id),
            self.dynamo.transact_delete_comment(self.id),
        ]
        self.dynamo.client.transact_write_items(transacts)

        # delete view records on the comment
        self.view_manager.delete_views(self.item['partitionKey'])
        return self
