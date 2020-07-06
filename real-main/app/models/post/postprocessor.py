import logging

import pendulum

from app.models.card.specs import CommentCardSpec

logger = logging.getLogger()


class PostPostProcessor:  # unfortunate namenaming
    def __init__(
        self,
        dynamo=None,
        view_dynamo=None,
        manager=None,
        card_manager=None,
        comment_manager=None,
        user_manager=None,
    ):
        self.dynamo = dynamo
        self.view_dynamo = view_dynamo
        self.manager = manager
        self.card_manager = card_manager
        self.comment_manager = comment_manager
        self.user_manager = user_manager

    def run(self, pk, sk, old_item, new_item):
        post_id = pk.split('/')[1]

        if sk == '-':
            # keep card in sync with unviewed comment count
            posted_by_user_id = (new_item or old_item)['postedByUserId']
            old_count = old_item.get('commentsUnviewedCount', 0)
            new_count = new_item.get('commentsUnviewedCount', 0)
            if old_count != new_count:
                if new_count > 0:
                    self.card_manager.add_or_update_card_by_spec(
                        CommentCardSpec(posted_by_user_id, post_id, unviewed_comments_count=new_count)
                    )
                else:
                    self.card_manager.remove_card_by_spec_if_exists(CommentCardSpec(posted_by_user_id, post_id))

        # could try to consolidate this in a FlagPostProcessor
        if sk.startswith('flag/'):
            user_id = sk.split('/')[1]
            if not old_item and new_item:
                self.post_flag_added(post_id, user_id)
            if old_item and not new_item:
                self.post_flag_deleted(post_id)

    def comment_added(self, post_id, commented_by_user_id, created_at):
        post_item = self.dynamo.get_post(post_id)
        posted_by_user_id = post_item['postedByUserId']
        by_post_owner = posted_by_user_id == commented_by_user_id
        self.dynamo.increment_comment_count(post_id, viewed=by_post_owner)
        if not by_post_owner:
            self.dynamo.set_last_unviewed_comment_at(post_item, created_at)

    def comment_deleted(self, post_id, comment_id, commented_by_user_id, created_at):
        post_item = self.dynamo.get_post(post_id)
        posted_by_user_id = post_item['postedByUserId'] if post_item else None
        self.dynamo.decrement_comment_count(post_id, fail_soft=True)

        # for each view of the comment delete the view record & keep track of whether it was the post owner's view
        comment_view_deleted = False
        for view_item in self.comment_manager.view_dynamo.generate_views(comment_id):
            user_id = view_item['sortKey'].split('/')[1]
            self.comment_manager.view_dynamo.delete_view(comment_id, user_id)
            comment_view_deleted = comment_view_deleted or (post_item and user_id == posted_by_user_id)

        if post_item and commented_by_user_id != posted_by_user_id:
            # has the post owner 'viewed' that comment via reporting a view on the post?
            post_view_item = self.view_dynamo.get_view(post_id, posted_by_user_id)
            post_last_viewed_at = pendulum.parse(post_view_item['lastViewedAt']) if post_view_item else None
            is_viewed = comment_view_deleted or (post_last_viewed_at and post_last_viewed_at > created_at)
            if not is_viewed:
                post_item = self.dynamo.decrement_comments_unviewed_count(post_id, fail_soft=True)
                # if the comment unviewed count hit zero, then remove post from 'posts with unviewed comments' index
                if post_item and post_item.get('commentsUnviewedCount', 0) == 0:
                    self.dynamo.set_last_unviewed_comment_at(post_item, None)

    def comment_view_added(self, post_id, user_id):
        post_item = self.dynamo.get_post(post_id)
        posted_by_user_id = post_item['postedByUserId']
        if user_id == posted_by_user_id:
            self.dynamo.decrement_comments_unviewed_count(post_id, fail_soft=True)

    def post_flag_added(self, post_id, user_id):
        post_item = self.dynamo.increment_flag_count(post_id)
        post = self.manager.init_post(post_item)

        # force archive the post?
        user = self.user_manager.get_user(user_id)
        if user.username in post.flag_admin_usernames or post.is_crowdsourced_forced_removal_criteria_met():
            logger.warning(f'Force archiving post `{post_id}` from flagging')
            post.archive(forced=True)

    def post_flag_deleted(self, post_id):
        self.dynamo.decrement_flag_count(post_id, fail_soft=True)
