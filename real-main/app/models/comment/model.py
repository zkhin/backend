import logging

from app.utils import ViewedStatus

from . import exceptions

logger = logging.getLogger()


class Comment:

    exceptions = exceptions

    def __init__(self, comment_item, comment_dynamo, post_manager=None, user_manager=None):
        self.dynamo = comment_dynamo
        self.post_manager = post_manager
        self.user_manager = user_manager
        self.item = comment_item
        self.id = comment_item['commentId']
        self.user_id = comment_item['userId']
        self.post_id = comment_item['postId']

    def serialize(self, caller_user_id):
        resp = self.item.copy()

        user = self.user_manager.get_user(self.user_id)
        resp['commentedBy'] = user.serialize(caller_user_id)

        if resp['userId'] == caller_user_id:  # author of the message
            resp['viewedStatus'] = ViewedStatus.VIEWED
        elif self.dynamo.get_comment_view(self.id, caller_user_id):
            resp['viewedStatus'] = ViewedStatus.VIEWED
        else:
            resp['viewedStatus'] = ViewedStatus.NOT_VIEWED

        return resp

    def delete(self):
        # order matters to moto (in test suite), but not on dynamo
        transacts = [
            self.post_manager.dynamo.transact_decrement_comment_count(self.post_id),
            self.dynamo.transact_delete_comment(self.id),
        ]
        self.dynamo.client.transact_write_items(transacts)

        # delete view records on the comment
        with self.dynamo.client.table.batch_writer() as batch:
            for key in self.dynamo.generate_comment_view_keys_by_comment(self.id):
                batch.delete_item(Key=key)

        return self
