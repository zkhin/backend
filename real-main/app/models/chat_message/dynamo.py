import logging

from boto3.dynamodb.conditions import Key
import pendulum

logger = logging.getLogger()


class ChatMessageDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def get_chat_message(self, message_id, strongly_consistent=False):
        return self.client.get_item({
            'partitionKey': f'chatMessage/{message_id}',
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

    def generate_chat_messages_by_chat(self, chat_id):
        query_kwargs = {
            'KeyConditionExpression': Key('gsiA1PartitionKey').eq(f'chatMessage/{chat_id}'),
            'IndexName': 'GSI-A1',
        }
        return self.client.generate_all_query(query_kwargs)
