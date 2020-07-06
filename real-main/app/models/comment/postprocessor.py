import logging

import pendulum

logger = logging.getLogger()


class CommentPostProcessor:
    def __init__(self, dynamo=None, manager=None, post_manager=None, user_manager=None):
        self.dynamo = dynamo
        self.manager = manager
        self.post_manager = post_manager
        self.user_manager = user_manager

    def run(self, pk, sk, old_item, new_item):
        comment_id = pk.split('/')[1]

        # comment added, edited or deleted
        if sk == '-':
            post_id = (new_item or old_item)['postId']
            user_id = (new_item or old_item)['userId']
            created_at = pendulum.parse((new_item or old_item)['commentedAt'])
            if not old_item and new_item:  # comment added?
                self.post_manager.postprocessor.comment_added(post_id, user_id, created_at)
                self.user_manager.postprocessor.comment_added(user_id)
            if old_item and not new_item:  # comment deleted?
                self.post_manager.postprocessor.comment_deleted(post_id, comment_id, user_id, created_at)
                self.user_manager.postprocessor.comment_deleted(user_id)

        # comment view added
        if sk.startswith('view/') and not old_item and new_item:
            user_id = sk.split('/')[1]
            comment_item = self.dynamo.get_comment(comment_id)
            self.post_manager.postprocessor.comment_view_added(comment_item['postId'], user_id)

        # could try to consolidate this in a FlagPostProcessor
        if sk.startswith('flag/'):
            user_id = sk.split('/')[1]
            if not old_item and new_item:
                self.comment_flag_added(comment_id, user_id)
            if old_item and not new_item:
                self.comment_flag_deleted(comment_id)

    def comment_flag_added(self, comment_id, user_id):
        comment_item = self.dynamo.increment_flag_count(comment_id)
        comment = self.manager.init_comment(comment_item)

        # force delete the comment?
        user = self.user_manager.get_user(user_id)
        if user.username in comment.flag_admin_usernames or comment.is_crowdsourced_forced_removal_criteria_met():
            logger.warning(f'Force deleting comment `{comment_id}` from flagging')
            comment.delete(forced=True)

    def comment_flag_deleted(self, comment_id):
        self.dynamo.decrement_flag_count(comment_id, fail_soft=True)
