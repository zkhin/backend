import logging

import boto3.dynamodb.conditions as conditions

logger = logging.getLogger()


class ChatMessageDynamo:
    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def pk(self, message_id):
        return {
            'partitionKey': f'chatMessage/{message_id}',
            'sortKey': '-',
        }

    def typed_pk(self, message_id):
        return {
            'partitionKey': {'S': f'chatMessage/{message_id}'},
            'sortKey': {'S': '-'},
        }

    def get_chat_message(self, message_id, strongly_consistent=False):
        return self.client.get_item(self.pk(message_id), ConsistentRead=strongly_consistent)

    def transact_add_chat_message(self, message_id, chat_id, author_user_id, text, text_tags, now):
        created_at_str = now.to_iso8601_string()
        query_kwargs = {
            'Put': {
                'Item': {
                    'schemaVersion': {'N': '0'},
                    'partitionKey': {'S': f'chatMessage/{message_id}'},
                    'sortKey': {'S': '-'},
                    'gsiA1PartitionKey': {'S': f'chatMessage/{chat_id}'},
                    'gsiA1SortKey': {'S': created_at_str},
                    'messageId': {'S': message_id},
                    'chatId': {'S': chat_id},
                    'createdAt': {'S': created_at_str},
                    'text': {'S': text},
                    'textTags': {
                        'L': [
                            {'M': {'tag': {'S': text_tag['tag']}, 'userId': {'S': text_tag['userId']},}}
                            for text_tag in text_tags
                        ]
                    },
                },
                'ConditionExpression': 'attribute_not_exists(partitionKey)',  # no updates, just adds
            }
        }
        if author_user_id:
            query_kwargs['Put']['Item']['userId'] = {'S': author_user_id}
        return query_kwargs

    def transact_edit_chat_message(self, message_id, text, text_tags, now):
        return {
            'Update': {
                'Key': self.typed_pk(message_id),
                'UpdateExpression': 'SET lastEditedAt = :at, #textName = :text, textTags = :textTags',
                'ExpressionAttributeNames': {'#textName': 'text',},
                'ExpressionAttributeValues': {
                    ':at': {'S': now.to_iso8601_string()},
                    ':text': {'S': text},
                    ':textTags': {
                        'L': [
                            {'M': {'tag': {'S': text_tag['tag']}, 'userId': {'S': text_tag['userId']},}}
                            for text_tag in text_tags
                        ]
                    },
                },
                'ConditionExpression': 'attribute_exists(partitionKey)',
            }
        }

    def transact_delete_chat_message(self, message_id):
        return {
            'Delete': {'Key': self.typed_pk(message_id), 'ConditionExpression': 'attribute_exists(partitionKey)',}
        }

    def generate_chat_messages_by_chat(self, chat_id, pks_only=False):
        query_kwargs = {
            'KeyConditionExpression': conditions.Key('gsiA1PartitionKey').eq(f'chatMessage/{chat_id}'),
            'IndexName': 'GSI-A1',
        }
        gen = self.client.generate_all_query(query_kwargs)
        if pks_only:
            gen = ({'partitionKey': item['partitionKey'], 'sortKey': item['sortKey']} for item in gen)
        return gen
