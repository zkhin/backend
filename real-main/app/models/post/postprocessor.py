import logging

logger = logging.getLogger()


class PostPostProcessor:  # unfortunate namenaming
    def __init__(self, dynamo=None, view_dynamo=None, manager=None, comment_manager=None):
        self.dynamo = dynamo
        self.view_dynamo = view_dynamo
        self.manager = manager
        self.comment_manager = comment_manager

    def run(self, pk, sk, old_item, new_item):
        # could try to consolidate this in a FlagPostProcessor
        if sk.startswith('flag/'):
            post_id = pk.split('/')[1]
            user_id = sk.split('/')[1]
            if not old_item and new_item:
                self.manager.on_flag_added(post_id, user_id)
            if old_item and not new_item:
                self.manager.on_flag_deleted(post_id)

    def comment_view_added(self, post_id, user_id):
        post_item = self.dynamo.get_post(post_id)
        posted_by_user_id = post_item['postedByUserId']
        if user_id == posted_by_user_id:
            self.dynamo.decrement_comments_unviewed_count(post_id, fail_soft=True)
