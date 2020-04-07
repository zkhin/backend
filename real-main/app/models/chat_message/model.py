import logging

import pendulum

from . import enums, exceptions

logger = logging.getLogger()


class ChatMessage:

    enums = enums
    exceptions = exceptions
    trigger_notification_mutation = '''
        mutation TriggerChatMessageNotification ($input: ChatMessageNotificationInput!) {
            triggerChatMessageNotification (input: $input) {
                userId
                type
                message {
                    messageId
                    chat {
                        chatId
                    }
                    authorUserId
                    author {
                        userId
                        username
                    }
                    text
                    textTaggedUsers {
                        tag
                        user {
                            userId
                        }
                    }
                    createdAt
                    lastEditedAt
                }
            }
        }
    '''

    def __init__(self, item, chat_message_dynamo, appsync_client=None, block_manager=None, chat_manager=None,
                 user_manager=None, view_manager=None):
        self.dynamo = chat_message_dynamo
        self.item = item
        self.appsync_client = appsync_client
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

        chat = self.chat_manager.get_chat(self.chat_id)
        chat.update_memberships_last_message_activity_at(now)

        self.refresh_item(strongly_consistent=True)
        return self

    def delete(self, now=None):
        now = now or pendulum.now('utc')
        transacts = [
            self.dynamo.transact_delete_chat_message(self.id),
            self.chat_manager.dynamo.transact_register_chat_message_deleted(self.chat_id, now),
        ]
        self.dynamo.client.transact_write_items(transacts)

        chat = self.chat_manager.get_chat(self.chat_id)
        chat.update_memberships_last_message_activity_at(now)

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
            self.trigger_notification(notification_type, user_id)
            already_notified_user_ids.add(user_id)

        for user_id in self.chat_manager.dynamo.generate_chat_membership_user_ids_by_chat(self.chat_id):
            if user_id in already_notified_user_ids:
                continue
            self.trigger_notification(notification_type, user_id)

    def trigger_notification(self, notification_type, user_id):
        author_username = None
        if (
            self.author
            and not self.block_manager.is_blocked(user_id, self.user_id)
            and not self.block_manager.is_blocked(self.user_id, user_id)
        ):
            author_username = self.author.username

        input_obj = {
            'userId': user_id,
            'messageId': self.id,
            'chatId': self.chat_id,
            'authorUserId': self.user_id,
            'authorUsername': author_username,
            'type': notification_type,
            'text': self.item['text'],
            'textTaggedUserIds': self.item.get('textTags', []),
            'createdAt': self.item['createdAt'],
            'lastEditedAt': self.item.get('lastEditedAt'),
        }
        self.appsync_client.send(self.trigger_notification_mutation, {'input': input_obj})
