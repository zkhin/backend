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
                messageId
                chatId
                authorUserId
                type
                text
                textTaggedUserIds {
                    tag
                    userId
                }
                createdAt
                lastEditedAt
            }
        }
    '''

    def __init__(self, item, chat_message_dynamo, appsync_client=None, chat_manager=None, user_manager=None,
                 view_manager=None):
        self.dynamo = chat_message_dynamo
        self.item = item
        self.appsync_client = appsync_client
        self.chat_manager = chat_manager
        self.user_manager = user_manager
        self.view_manager = view_manager
        # immutables
        self.id = item['messageId']
        self.chat_id = self.item['chatId']
        self.user_id = self.item['userId']

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

    def trigger_notification(self, notification_type):
        variables = {'input': {
            'messageId': self.id,
            'chatId': self.chat_id,
            'authorUserId': self.user_id,
            'type': notification_type,
            'text': self.item['text'],
            'textTaggedUserIds': self.item.get('textTags', []),
            'createdAt': self.item['createdAt'],
            'lastEditedAt': self.item.get('lastEditedAt'),
        }}
        self.appsync_client.send(self.trigger_notification_mutation, variables)
