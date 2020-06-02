import collections
import logging

import boto3.dynamodb.conditions as conditions
import pendulum

logger = logging.getLogger()


class AlbumDynamo:
    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def pk(self, album_id):
        return {
            'partitionKey': f'album/{album_id}',
            'sortKey': '-',
        }

    def typed_pk(self, album_id):
        return {
            'partitionKey': {'S': f'album/{album_id}'},
            'sortKey': {'S': '-'},
        }

    def get_album(self, album_id, strongly_consistent=False):
        return self.client.get_item(self.pk(album_id), ConsistentRead=strongly_consistent)

    def transact_add_album(self, album_id, user_id, name, description=None, created_at=None):
        created_at = created_at or pendulum.now('utc')
        created_at_str = created_at.to_iso8601_string()
        query_kwargs = {
            'Put': {
                'Item': {
                    'schemaVersion': {'N': '0'},
                    'partitionKey': {'S': f'album/{album_id}'},
                    'sortKey': {'S': '-'},
                    'gsiA1PartitionKey': {'S': f'album/{user_id}'},
                    'gsiA1SortKey': {'S': created_at_str},
                    'albumId': {'S': album_id},
                    'ownedByUserId': {'S': user_id},
                    'createdAt': {'S': created_at_str},
                    'name': {'S': name},
                },
                'ConditionExpression': 'attribute_not_exists(partitionKey)',  # no updates, just adds
            }
        }
        if description is not None:
            query_kwargs['Put']['Item']['description'] = {'S': description}
        return query_kwargs

    def set(self, album_id, name=None, description=None):
        assert name is not None or description is not None, 'Action-less post edit requested'
        assert name != '', 'All albums must have names'

        exp_actions = collections.defaultdict(list)
        exp_values = {}
        exp_names = {}

        if name is not None:
            exp_actions['SET'].append('#name = :name')
            exp_names['#name'] = 'name'
            exp_values[':name'] = name

        if description is not None:
            # empty string deletes
            if description == '':
                exp_actions['REMOVE'].append('description')
            else:
                exp_actions['SET'].append('description = :description')
                exp_values[':description'] = description

        update_query_kwargs = {
            'Key': self.pk(album_id),
            'UpdateExpression': ' '.join([f'{k} {", ".join(v)}' for k, v in exp_actions.items()]),
        }
        if exp_names:
            update_query_kwargs['ExpressionAttributeNames'] = exp_names
        if exp_values:
            update_query_kwargs['ExpressionAttributeValues'] = exp_values
        return self.client.update_item(update_query_kwargs)

    def set_album_art_hash(self, album_id, art_hash):
        update_query_kwargs = {
            'Key': self.pk(album_id),
        }

        if art_hash:
            update_query_kwargs['UpdateExpression'] = 'SET artHash = :ah'
            update_query_kwargs['ExpressionAttributeValues'] = {':ah': art_hash}
        else:
            update_query_kwargs['UpdateExpression'] = 'REMOVE artHash'

        return self.client.update_item(update_query_kwargs)

    def transact_delete_album(self, album_id):
        return {'Delete': {'Key': self.typed_pk(album_id), 'ConditionExpression': 'attribute_exists(partitionKey)',}}

    def transact_add_post(self, album_id, old_rank_count=None, now=None):
        "Transaction to change album properties to reflect adding a post to the album"
        now = now or pendulum.now('utc')
        query_kwargs = {
            'Update': {
                'Key': self.typed_pk(album_id),
                'UpdateExpression': 'ADD postCount :one, rankCount :one SET postsLastUpdatedAt = :now',
                'ExpressionAttributeValues': {':one': {'N': '1'}, ':now': {'S': now.to_iso8601_string()},},
                'ConditionExpression': 'attribute_exists(partitionKey)',
            }
        }

        if old_rank_count is not None:
            query_kwargs['Update']['ExpressionAttributeValues'][':rc'] = {'N': str(old_rank_count)}
            query_kwargs['Update']['ConditionExpression'] += ' and rankCount = :rc'
        else:
            query_kwargs['Update']['ConditionExpression'] += ' and attribute_not_exists(rankCount)'

        return query_kwargs

    def transact_remove_post(self, album_id, now=None):
        "Transaction to change album properties to reflect removing a post from the album"
        now = now or pendulum.now('utc')
        query_kwargs = {
            'Update': {
                'Key': self.typed_pk(album_id),
                'UpdateExpression': 'ADD postCount :negative_one SET postsLastUpdatedAt = :now',
                'ExpressionAttributeValues': {
                    ':negative_one': {'N': '-1'},
                    ':now': {'S': now.to_iso8601_string()},
                    ':zero': {'N': '0'},
                },
                'ConditionExpression': 'attribute_exists(partitionKey) and postCount > :zero',
            }
        }
        return query_kwargs

    def transact_increment_rank_count(self, album_id, old_rank_count, now=None):
        "Transaction to change album properties to reflect adding a post to the album"
        now = now or pendulum.now('utc')
        query_kwargs = {
            'Update': {
                'Key': self.typed_pk(album_id),
                'UpdateExpression': 'ADD rankCount :one SET postsLastUpdatedAt = :now',
                'ExpressionAttributeValues': {
                    ':one': {'N': '1'},
                    ':now': {'S': now.to_iso8601_string()},
                    ':rc': {'N': str(old_rank_count)},
                },
                'ConditionExpression': 'attribute_exists(partitionKey) and rankCount = :rc',
            }
        }
        return query_kwargs

    def generate_by_user(self, user_id):
        query_kwargs = {
            'KeyConditionExpression': conditions.Key('gsiA1PartitionKey').eq(f'album/{user_id}'),
            'IndexName': 'GSI-A1',
        }
        return self.client.generate_all_query(query_kwargs)
