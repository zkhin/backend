import decimal
import json
import logging

import pendulum

from app.models.block.enums import BlockStatus

from . import enums, exceptions

logger = logging.getLogger()


class DecimalJsonEncoder(json.JSONEncoder):
    "Helper class that can handle encoding decimals into json (as floats, percision lost)"
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        return super(DecimalJsonEncoder, self).default(obj)


class ChatMessage:

    enums = enums
    exceptions = exceptions

    def __init__(self, item, chat_message_dynamo=None, chat_message_appsync=None, block_manager=None,
                 chat_manager=None, user_manager=None, view_manager=None):
        self.dynamo = chat_message_dynamo
        self.appsync = chat_message_appsync

        self.item = item
        self.block_manager = block_manager
        self.chat_manager = chat_manager
        self.user_manager = user_manager
        self.view_manager = view_manager
        # immutables
        self.id = item['messageId']
        self.chat_id = self.item['chatId']
        self.user_id = self.item.get('userId')  # system messages have no userId

    @property
    def author(self):
        if not hasattr(self, '_author'):
            self._author = self.user_manager.get_user(self.user_id) if self.user_id else None
        return self._author

    def refresh_item(self, strongly_consistent=False):
        self.item = self.dynamo.get_chat_message(self.id, strongly_consistent=strongly_consistent)
        return self

    def serialize(self, caller_user_id):
        resp = self.item.copy()
        resp['author'] = self.user_manager.get_user(self.user_id).serialize(caller_user_id)
        resp['viewedStatus'] = self.view_manager.get_viewed_status(self, caller_user_id)
        return resp

    def edit(self, text, now=None):
        now = now or pendulum.now('utc')
        text_tags = self.user_manager.get_text_tags(text)

        transacts = [
            self.dynamo.transact_edit_chat_message(self.id, text, text_tags, now=now),
            self.chat_manager.dynamo.transact_register_chat_message_edited(self.chat_id, now),
        ]
        self.dynamo.client.transact_write_items(transacts)

        self.chat_manager.dynamo.update_all_chat_memberships_last_message_activity_at(self.chat_id, now)
        self.refresh_item(strongly_consistent=True)
        return self

    def delete(self, now=None):
        now = now or pendulum.now('utc')
        transacts = [
            self.dynamo.transact_delete_chat_message(self.id),
            self.chat_manager.dynamo.transact_register_chat_message_deleted(self.chat_id, now),
        ]
        self.dynamo.client.transact_write_items(transacts)

        self.chat_manager.dynamo.update_all_chat_memberships_last_message_activity_at(self.chat_id, now)
        return self

    def trigger_notifications(self, notification_type, user_ids=None):
        """
        Trigger onChatMessageNotification to be sent to clients.

        The `user_ids` parameter can be used to ensure that messages will be
        sent to those user_ids even if they aren't found as members in the DB.
        This is useful when members of the chat have just been added and thus
        dynamo may not have converged yet.
        """
        user_ids = user_ids or []
        already_notified_user_ids = set([self.user_id])  # don't notify the msg author

        for user_id in user_ids:
            if user_id in already_notified_user_ids:
                continue
            self.appsync.trigger_notification(notification_type, user_id, self)
            already_notified_user_ids.add(user_id)

        for user_id in self.chat_manager.dynamo.generate_chat_membership_user_ids_by_chat(self.chat_id):
            if user_id in already_notified_user_ids:
                continue
            self.appsync.trigger_notification(notification_type, user_id, self)

    def get_author_encoded(self, user_id):
        """
        Return the author in a serialized, stringified form if they exist and there is no
        blocking relationship between the given user and the author.
        """
        if not self.author:
            return None
        serialized = self.author.serialize(user_id)
        if serialized['blockerStatus'] == BlockStatus.BLOCKING:
            return None
        serialized['blockedStatus'] = self.block_manager.get_block_status(user_id, self.author.id)
        if serialized['blockedStatus'] == BlockStatus.BLOCKING:
            return None
        return json.dumps(serialized, cls=DecimalJsonEncoder)
