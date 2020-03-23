import logging

from boto3.dynamodb.conditions import Key
import pendulum

from .enums import ChatType

logger = logging.getLogger()


class ChatDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def get_chat(self, chat_id, strongly_consistent=False):
        return self.client.get_item({
            'partitionKey': f'chat/{chat_id}',
            'sortKey': '-',
        }, strongly_consistent=strongly_consistent)

    def get_chat_membership(self, chat_id, user_id, strongly_consistent=False):
        return self.client.get_item({
            'partitionKey': f'chat/{chat_id}',
            'sortKey': f'member/{user_id}',
        }, strongly_consistent=strongly_consistent)

    def get_direct_chat(self, user_id_1, user_id_2):
        user_ids = sorted([user_id_1, user_id_2])
        query_kwargs = {
            'KeyConditionExpression': Key('gsiA1PartitionKey').eq(f'chat/{user_ids[0]}/{user_ids[1]}'),
            'IndexName': 'GSI-A1',
        }
        return self.client.query_head(query_kwargs)

    def transact_add_chat(self, chat_id, chat_type, user_ids=None, name=None, now=None):
        # user_ids parameter is required for direct chats, forbidden for group
        if (chat_type == ChatType.DIRECT):
            assert user_ids and len(user_ids) == 2, 'DIRECT chats require user_ids parameter'
        if (chat_type == ChatType.GROUP):
            assert user_ids is None, 'GROUP chat forbit user_ids parameter'

        now = now or pendulum.now('utc')
        created_at_str = now.to_iso8601_string()
        query_kwargs = {'Put': {
            'Item': {
                'schemaVersion': {'N': '0'},
                'partitionKey': {'S': f'chat/{chat_id}'},
                'sortKey': {'S': '-'},
                'chatId': {'S': chat_id},
                'chatType': {'S': chat_type},
                'createdAt': {'S': created_at_str},
            },
            'ConditionExpression': 'attribute_not_exists(partitionKey)',  # no updates, just adds
        }}
        if name:
            query_kwargs['Put']['Item']['name'] = {'S': name}
        if user_ids:
            user_ids = sorted(user_ids)
            query_kwargs['Put']['Item']['userCount'] = {'N': str(len(user_ids))}
            query_kwargs['Put']['Item']['gsiA1PartitionKey'] = {'S': f'chat/{user_ids[0]}/{user_ids[1]}'}
            query_kwargs['Put']['Item']['gsiA1SortKey'] = {'S': '-'}
        return query_kwargs

    def transact_delete_chat(self, chat_id):
        return {'Delete': {
            'Key': {
                'partitionKey': {'S': f'chat/{chat_id}'},
                'sortKey': {'S': '-'},
            },
            'ConditionExpression': 'attribute_exists(partitionKey)',
        }}

    def transact_add_chat_membership(self, chat_id, user_id, now=None):
        now = now or pendulum.now('utc')
        joined_at_str = now.to_iso8601_string()
        return {'Put': {
            'Item': {
                'schemaVersion': {'N': '0'},
                'partitionKey': {'S': f'chat/{chat_id}'},
                'sortKey': {'S': f'member/{user_id}'},
                'gsiK1PartitionKey': {'S': f'chat/{chat_id}'},
                'gsiK1SortKey': {'S': f'member/{joined_at_str}'},
                'gsiK2PartitionKey': {'S': f'member/{user_id}'},
                'gsiK2SortKey': {'S': f'chat/{joined_at_str}'},
            },
            'ConditionExpression': 'attribute_not_exists(partitionKey)',  # no updates, just adds
        }}

    def transact_delete_chat_membership(self, chat_id, user_id):
        return {'Delete': {
            'Key': {
                'partitionKey': {'S': f'chat/{chat_id}'},
                'sortKey': {'S': f'member/{user_id}'},
            },
            'ConditionExpression': 'attribute_exists(partitionKey)',
        }}

    def transact_register_chat_message_added(self, chat_id, now):
        last_message_at_str = now.to_iso8601_string()
        return {'Update': {
            'Key': {
                'partitionKey': {'S': f'chat/{chat_id}'},
                'sortKey': {'S': '-'},
            },
            'UpdateExpression': 'ADD messageCount :one SET lastMessageAt = :lma',
            'ExpressionAttributeValues': {
                ':one': {'N': '1'},
                ':lma': {'S': last_message_at_str}
            },
            'ConditionExpression': 'attribute_exists(partitionKey) and not lastMessageAt > :lma',
        }}

    def generate_chat_membership_user_ids_by_chat(self, chat_id):
        query_kwargs = {
            'KeyConditionExpression': (
                Key('gsiK1PartitionKey').eq(f'chat/{chat_id}')
                & Key('gsiK1SortKey').begins_with('member/')
            ),
            'IndexName': 'GSI-K1',
        }
        return map(
            lambda item: item['sortKey'][len('member/'):],
            self.client.generate_all_query(query_kwargs),
        )

    def generate_chat_membership_chat_ids_by_user(self, user_id):
        query_kwargs = {
            'KeyConditionExpression': (
                Key('gsiK2PartitionKey').eq(f'member/{user_id}')
                & Key('gsiK2SortKey').begins_with('chat/')
            ),
            'IndexName': 'GSI-K2',
        }
        return map(
            lambda item: item['partitionKey'][len('chat/'):],
            self.client.generate_all_query(query_kwargs),
        )
