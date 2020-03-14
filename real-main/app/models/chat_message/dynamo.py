import logging

from boto3.dynamodb.conditions import Key
import pendulum

from . import exceptions

logger = logging.getLogger()


class ChatMessageDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def get_chat_message(self, message_id, strongly_consistent=False):
        return self.client.get_item({
            'partitionKey': f'chatMessage/{message_id}',
            'sortKey': '-',
        }, strongly_consistent=strongly_consistent)

    def get_chat_view_message(self, message_id, viewed_by_user_id, strongly_consistent=False):
        return self.client.get_item({
            'partitionKey': f'chatMessageView/{message_id}/{viewed_by_user_id}',
            'sortKey': '-',
        }, strongly_consistent=strongly_consistent)

    def transact_add_chat_message(self, message_id, chat_id, author_user_id, text, text_tags, now=None):
        now = now or pendulum.now('utc')
        created_at_str = now.to_iso8601_string()
        return {'Put': {
            'Item': {
                'schemaVersion': {'N': '0'},
                'partitionKey': {'S': f'chatMessage/{message_id}'},
                'sortKey': {'S': '-'},
                'gsiA1PartitionKey': {'S': f'chatMessage/{chat_id}'},
                'gsiA1SortKey': {'S': created_at_str},
                'messageId': {'S': message_id},
                'chatId': {'S': chat_id},
                'userId': {'S': author_user_id},
                'createdAt': {'S': created_at_str},
                'text': {'S': text},
                'textTags': {'L': [
                    {'M': {
                        'tag': {'S': text_tag['tag']},
                        'userId': {'S': text_tag['userId']},
                    }}
                    for text_tag in text_tags
                ]},
            },
            'ConditionExpression': 'attribute_not_exists(partitionKey)',  # no updates, just adds
        }}

    def add_chat_message_view(self, message_id, viewed_by_user_id, viewed_at):
        viewed_at_str = viewed_at.to_iso8601_string()
        transacts = [{
            'Put': {
                'Item': {
                    'schemaVersion': {'N': '0'},
                    'partitionKey': {'S': f'chatMessageView/{message_id}/{viewed_by_user_id}'},
                    'sortKey': {'S': '-'},
                    'gsiK1PartitionKey': {'S': f'chatMessageView/{message_id}'},
                    'gsiK1SortKey': {'S': viewed_at_str},
                    'messageId': {'S': message_id},
                    'userId': {'S': viewed_by_user_id},
                    'viewedAt': {'S': viewed_at_str},
                },
                'ConditionExpression': 'attribute_not_exists(partitionKey)',  # no updates, just adds
            },
        }, {
            'ConditionCheck': {
                'Key': {
                    'partitionKey': {'S': f'chatMessage/{message_id}'},
                    'sortKey': {'S': '-'},
                },
                'ExpressionAttributeValues': {
                    ':uid': {'S': viewed_by_user_id},
                },
                # message exists, and that the viewer is not the message author
                'ConditionExpression': 'attribute_exists(partitionKey) and userId <> :uid',
            },
        }]
        transact_exceptions = [
            exceptions.ChatMessageException('Chat message view already exists'),
            exceptions.ChatMessageException('Chat message does not exist or exists but viewer is author'),
        ]
        self.client.transact_write_items(transacts, transact_exceptions)

    def generate_chat_messages_by_chat(self, chat_id):
        query_kwargs = {
            'KeyConditionExpression': Key('gsiA1PartitionKey').eq(f'chatMessage/{chat_id}'),
            'IndexName': 'GSI-A1',
        }
        return self.client.generate_all_query(query_kwargs)

    def generate_chat_message_viewed_by_user_ids_by_message(self, message_id):
        query_kwargs = {
            'KeyConditionExpression': Key('gsiK1PartitionKey').eq(f'chatMessageView/{message_id}'),
            'IndexName': 'GSI-K1',
        }
        return map(
            lambda item: item['partitionKey'].split('/')[2],
            self.client.generate_all_query(query_kwargs),
        )
