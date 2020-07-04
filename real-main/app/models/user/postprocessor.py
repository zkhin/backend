import logging

from app.models.card.specs import ChatCardSpec, RequestedFollowersCardSpec

from .enums import UserStatus

logger = logging.getLogger()


class UserPostProcessor:
    def __init__(
        self, dynamo=None, manager=None, elasticsearch_client=None, pinpoint_client=None, card_manager=None
    ):
        self.dynamo = dynamo
        self.manager = manager
        self.elasticsearch_client = elasticsearch_client
        self.pinpoint_client = pinpoint_client
        self.card_manager = card_manager

    def run(self, pk, sk, old_item, new_item):
        assert sk == 'profile', 'Should only be called for user profile item'
        user_id = pk[len('user/') :]
        self.handle_elasticsearch(user_id, old_item, new_item)
        self.handle_pinpoint(user_id, old_item, new_item)
        self.handle_requested_followers_card(user_id, old_item, new_item)
        self.handle_chats_with_new_messages_card(user_id, old_item, new_item)

        if new_item.get('commentForcedDeletionCount', 0) > old_item.get('commentForcedDeletionCount', 0):
            self.forced_comment_deletion(new_item)

        if new_item.get('postForcedArchivingCount', 0) > old_item.get('postForcedArchivingCount', 0):
            self.forced_post_archiving(new_item)

    def handle_elasticsearch(self, user_id, old_item, new_item):
        # if we're manually rebuilding the index, treat everything as new
        new_reindexed_at = new_item.get('lastManuallyReindexedAt')
        old_reindexed_at = old_item.get('lastManuallyReindexedAt')
        if new_reindexed_at and new_reindexed_at != old_reindexed_at:
            old_item = {}

        if new_item and old_item:
            self.elasticsearch_client.update_user(user_id, old_item, new_item)
        if new_item and not old_item:
            self.elasticsearch_client.add_user(user_id, new_item)
        if not new_item and old_item:
            self.elasticsearch_client.delete_user(user_id)

    def handle_pinpoint(self, user_id, old_item, new_item):
        # check if this was a user deletion
        if old_item and not new_item:
            self.pinpoint_client.delete_user_endpoints(user_id)
            return

        # check for a change of email, phone
        for dynamo_name, pinpoint_name in (('email', 'EMAIL'), ('phoneNumber', 'SMS')):
            value = new_item.get(dynamo_name)
            if old_item.get(dynamo_name) == value:
                continue
            if value:
                self.pinpoint_client.update_user_endpoint(user_id, pinpoint_name, value)
            else:
                self.pinpoint_client.delete_user_endpoint(user_id, pinpoint_name)

        # check if this was a change in user status
        status = new_item.get('userStatus', UserStatus.ACTIVE)
        if old_item and old_item.get('userStatus', UserStatus.ACTIVE) != status:
            if status == UserStatus.ACTIVE:
                self.pinpoint_client.enable_user_endpoints(user_id)
            if status == UserStatus.DISABLED:
                self.pinpoint_client.disable_user_endpoints(user_id)
            if status == UserStatus.DELETING:
                self.pinpoint_client.delete_user_endpoints(user_id)

    def handle_requested_followers_card(self, user_id, old_item, new_item):
        old_cnt = old_item.get('followersRequestedCount', 0)
        new_cnt = new_item.get('followersRequestedCount', 0)
        if new_cnt == old_cnt:
            return
        if new_cnt > 0:
            self.card_manager.add_or_update_card_by_spec(
                RequestedFollowersCardSpec(user_id, requested_followers_count=new_cnt)
            )
        else:
            self.card_manager.remove_card_by_spec_if_exists(RequestedFollowersCardSpec(user_id))

    def handle_chats_with_new_messages_card(self, user_id, old_item, new_item):
        old_cnt = old_item.get('chatsWithUnviewedMessagesCount', 0)
        new_cnt = new_item.get('chatsWithUnviewedMessagesCount', 0)
        if new_cnt == old_cnt:
            return
        if new_cnt > 0:
            self.card_manager.add_or_update_card_by_spec(
                ChatCardSpec(user_id, chats_with_unviewed_messages_count=new_cnt)
            )
        else:
            self.card_manager.remove_card_by_spec_if_exists(ChatCardSpec(user_id))

    def forced_comment_deletion(self, new_item):
        user = self.manager.init_user(new_item)
        if user.is_forced_disabling_criteria_met_by_comments():
            user.disable()
            # the string USER_FORCE_DISABLED is hooked up to a cloudwatch metric & alert
            logger.warning(
                f'USER_FORCE_DISABLED: user `{user.id}` with username `{user.username}` disabled due to comments'
            )

    def forced_post_archiving(self, new_item):
        user = self.manager.init_user(new_item)
        if user.is_forced_disabling_criteria_met_by_posts():
            user.disable()
            # the string USER_FORCE_DISABLED is hooked up to a cloudwatch metric & alert
            logger.warning(
                f'USER_FORCE_DISABLED: user `{user.id}` with username `{user.username}` disabled due to posts'
            )

    def comment_added(self, user_id):
        self.dynamo.increment_comment_count(user_id)

    def comment_deleted(self, user_id):
        self.dynamo.decrement_comment_count(user_id, fail_soft=True)
        self.dynamo.increment_comment_deleted_count(user_id)
