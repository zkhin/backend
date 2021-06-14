import logging

import pendulum
from boto3.dynamodb.conditions import Key

from ..enums import ChatType
from ..exceptions import ChatAlreadyExists

logger = logging.getLogger()


class ChatDynamo:
    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def pk(self, chat_id):
        return {
            'partitionKey': f'chat/{chat_id}',
            'sortKey': '-',
        }

    def get(self, chat_id, strongly_consistent=False):
        return self.client.get_item(self.pk(chat_id), ConsistentRead=strongly_consistent)

    def get_direct_chat(self, user_id_1, user_id_2):
        user_ids = sorted([user_id_1, user_id_2])
        query_kwargs = {
            'KeyConditionExpression': Key('gsiA1PartitionKey').eq(f'chat/{user_ids[0]}/{user_ids[1]}'),
            'IndexName': 'GSI-A1',
        }
        return self.client.query_head(query_kwargs)

    def add(
        self,
        chat_id,
        chat_type,
        user_id,
        with_user_ids,
        initial_message_text,
        initial_message_id=None,
        name=None,
        now=None,
    ):
        if chat_type == ChatType.DIRECT:
            assert len(with_user_ids) == 1, 'DIRECT chats require exactly two participants'
            assert name is None, 'DIRECT chats cannot be named'

        now = now or pendulum.now('utc')
        initial_user_ids = sorted([user_id, *with_user_ids])
        item = {
            **self.pk(chat_id),
            'schemaVersion': 0,
            'chatId': chat_id,
            'chatType': chat_type,
            'createdAt': now.to_iso8601_string(),
            'createdByUserId': user_id,
            'initialMemberUserIds': initial_user_ids,
            'initialMessageText': initial_message_text,
            **({'initialMessageId': initial_message_id} if initial_message_id else {}),
            **({'name': name} if name else {}),
            **(
                {
                    'gsiA1PartitionKey': '/'.join(['chat', *initial_user_ids]),
                    'gsiA1SortKey': '-',
                }
                if chat_type == ChatType.DIRECT
                else {}
            ),
        }
        try:
            return self.client.add_item({'Item': item})
        except self.client.exceptions.ConditionalCheckFailedException as err:
            raise ChatAlreadyExists(chat_id) from err

    def update_name(self, chat_id, name):
        "Set `name` to empty string to delete"
        query_kwargs = {
            'Key': self.pk(chat_id),
            'ExpressionAttributeNames': {'#name': 'name'},
        }
        if name:
            query_kwargs['UpdateExpression'] = 'SET #name = :name'
            query_kwargs['ExpressionAttributeValues'] = {':name': name}
        else:
            query_kwargs['UpdateExpression'] = 'REMOVE #name'
        return self.client.update_item(query_kwargs)

    def update_last_message_activity_at(self, chat_id, now):
        now_str = now.to_iso8601_string()
        query_kwargs = {
            'Key': self.pk(chat_id),
            'UpdateExpression': 'SET lastMessageActivityAt = :at',
            'ExpressionAttributeValues': {':at': now_str},
            'ConditionExpression': 'attribute_exists(partitionKey) AND NOT :at < lastMessageActivityAt',
        }
        msg = f'Failed to update last message activity for chat `{chat_id}` to `{now_str}`'
        return self.client.update_item(query_kwargs, failure_warning=msg)

    def increment_flag_count(self, chat_id):
        return self.client.increment_count(self.pk(chat_id), 'flagCount')

    def decrement_flag_count(self, chat_id):
        return self.client.decrement_count(self.pk(chat_id), 'flagCount')

    def increment_messages_count(self, chat_id):
        return self.client.increment_count(self.pk(chat_id), 'messagesCount')

    def decrement_messages_count(self, chat_id):
        return self.client.decrement_count(self.pk(chat_id), 'messagesCount')

    def increment_user_count(self, chat_id):
        return self.client.increment_count(self.pk(chat_id), 'userCount')

    def decrement_user_count(self, chat_id):
        return self.client.decrement_count(self.pk(chat_id), 'userCount')

    def delete(self, chat_id):
        return self.client.delete_item(self.pk(chat_id))
