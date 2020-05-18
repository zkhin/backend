import logging

from app.models.user.enums import UserStatus

from . import enums, exceptions

logger = logging.getLogger()


class FlagModelMixin:

    flag_enums = enums
    flag_exceptions = exceptions

    # users that have flagging superpowers
    flag_admin_usernames = ('real', 'ian')

    def __init__(self, flag_dynamo=None):
        # TODO: add a super().__init__()
        if flag_dynamo:
            self.flag_dynamo = flag_dynamo

    def flag(self, user):
        # can't flag a model of a user that has blocked us
        if self.block_manager.is_blocked(self.user_id, user.id):
            raise exceptions.FlagException(f'User has been blocked by owner of {self.item_type} `{self.id}`')

        # can't flag a model of a user we have blocked
        if self.block_manager.is_blocked(user.id, self.user_id):
            raise exceptions.FlagException(f'User has blocked owner of {self.item_type} `{self.id}`')

        # cant flag our own model
        if user.id == self.user_id:
            raise exceptions.FlagException(f'User cant flag their own {self.item_type} `{self.id}`')

        # write to the db
        transacts = [
            self.flag_dynamo.transact_add(self.id, user.id),
            self.dynamo.transact_increment_flag_count(self.id),
        ]
        transact_exceptions = [
            exceptions.AlreadyFlagged(self.item_type, self.id, user.id),
            self.exceptions.dne(self.id)
        ]
        self.flag_dynamo.client.transact_write_items(transacts, transact_exceptions)
        self.item['flagCount'] = self.item.get('flagCount', 0) + 1

        # force archive the item?
        if user.username in self.flag_admin_usernames or self.is_crowdsourced_forced_removal_criteria_met():
            logger.warning(f'Force removing {self.item_type} `{self.id}`')
            self.remove_from_flagging()

            # force disable the user?
            self.user.refresh_item(strongly_consistent=True)
            if self.is_user_forced_disabling_criteria_met():
                logger.warning(f'Force disabling user `{self.user.id}`')
                self.user.set_user_status(UserStatus.DISABLED)
                # the string USER_FORCE_DISABLED is hooked up to a cloudwatch metric & alert
                logger.warning(f'USER_FORCE_DISABLED: user `{self.user.id}` with username `{self.user.username}`')

        return self

    def unflag(self, user_id):
        transacts = [
            self.flag_dynamo.transact_delete(self.id, user_id),
            self.dynamo.transact_decrement_flag_count(self.id),
        ]
        transact_exceptions = [
            exceptions.NotFlagged(self.item_type, self.id, user_id),
            self.exceptions.generic(f'Post `{self.id}` does not exist or has no flagCount'),
        ]
        self.flag_dynamo.client.transact_write_items(transacts, transact_exceptions)

        self.item['flagCount'] = self.item.get('flagCount', 0) - 1
        return self

    def remove_from_flagging(self):
        raise NotImplementedError('Must be implemented by model class')

    def is_user_forced_disabling_criteria_met(self):
        raise NotImplementedError('Must be implemented by model class')

    def is_crowdsourced_forced_removal_criteria_met(self):
        # the item should be force-archived if (directly from spec):
        #   - over 5 users have viewed the item and
        #   - at least 10% of them have flagged it
        viewed_by_count = self.item.get('viewedByCount', 0)
        flag_count = self.item.get('flagCount', 0)
        if viewed_by_count > 5 and flag_count > viewed_by_count / 10:
            return True
        return False
