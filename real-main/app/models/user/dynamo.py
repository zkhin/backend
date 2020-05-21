import collections
import logging

import boto3.dynamodb.conditions as conditions
import pendulum

from app.models.post.enums import PostStatus

from .enums import UserPrivacyStatus, UserStatus
from .exceptions import UserAlreadyExists, UserDoesNotExist

logger = logging.getLogger()


class UserDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def pk(self, user_id):
        return {
            'partitionKey': f'user/{user_id}',
            'sortKey': 'profile',
        }

    def typed_pk(self, user_id):
        return {
            'partitionKey': {'S': f'user/{user_id}'},
            'sortKey': {'S': 'profile'},
        }

    def get_user(self, user_id, strongly_consistent=False):
        return self.client.get_item(self.pk(user_id), ConsistentRead=strongly_consistent)

    def get_user_by_username(self, username):
        query_kwargs = {
            'KeyConditionExpression': conditions.Key('gsiA1PartitionKey').eq(f'username/{username}'),
            'IndexName': 'GSI-A1',
        }
        return self.client.query_head(query_kwargs)

    def delete_user(self, user_id):
        return self.client.delete_item(self.pk(user_id))

    def add_user(self, user_id, username, full_name=None, email=None, phone=None, placeholder_photo_code=None,
                 now=None):
        now = now or pendulum.now('utc')
        query_kwargs = {
            'Item': {
                'schemaVersion': 8,
                'partitionKey': f'user/{user_id}',
                'sortKey': 'profile',
                'gsiA1PartitionKey': f'username/{username}',
                'gsiA1SortKey': '-',
                'userId': user_id,
                'username': username,
                'privacyStatus': UserPrivacyStatus.PUBLIC,
                'signedUpAt': now.to_iso8601_string(),
            },
        }
        if full_name:
            query_kwargs['Item']['fullName'] = full_name
        if placeholder_photo_code:
            query_kwargs['Item']['placeholderPhotoCode'] = placeholder_photo_code
        if email:
            query_kwargs['Item']['email'] = email
        if phone:
            query_kwargs['Item']['phoneNumber'] = phone
        try:
            return self.client.add_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException:
            raise UserAlreadyExists(user_id)

    def update_user_username(self, user_id, username, old_username, now=None):
        now = now or pendulum.now('utc')
        query_kwargs = {
            'Key': self.pk(user_id),
            'UpdateExpression': 'SET ' + ', '.join([
                'username = :un',
                'usernameLastValue = :oldun',
                'usernameLastChangedAt = :ulca',
                'gsiA1PartitionKey = :gsia1pk',
            ]),
            'ExpressionAttributeValues': {
                ':un': username,
                ':oldun': old_username,
                ':ulca': now.to_iso8601_string(),
                ':gsia1pk': f'username/{username}',
            },
            'ConditionExpression': 'username = :oldun',
        }
        return self.client.update_item(query_kwargs)

    def set_user_photo_post_id(self, user_id, photo_id):
        query_kwargs = {
            'Key': self.pk(user_id),
        }

        if photo_id:
            query_kwargs['UpdateExpression'] = 'SET photoPostId = :ppid'
            query_kwargs['ExpressionAttributeValues'] = {':ppid': photo_id}
        else:
            query_kwargs['UpdateExpression'] = 'REMOVE photoPostId'

        return self.client.update_item(query_kwargs)

    def set_user_status(self, user_id, status, now=None):
        assert status in UserStatus._ALL, f'Invalid UserStatus `{status}`'
        now = now or pendulum.now('utc')
        query_kwargs = {
            'Key': self.pk(user_id),
        }
        if status == UserStatus.ACTIVE:  # default value
            query_kwargs['UpdateExpression'] = 'REMOVE userStatus'
        else:
            query_kwargs['UpdateExpression'] = 'SET userStatus = :s'
            query_kwargs['ExpressionAttributeValues'] = {':s': status}
        if status == UserStatus.DISABLED:
            query_kwargs['UpdateExpression'] += ', lastDisabledAt = :lda'
            query_kwargs['ExpressionAttributeValues'][':lda'] = now.to_iso8601_string()
        return self.client.update_item(query_kwargs)

    def set_user_privacy_status(self, user_id, privacy_status):
        assert privacy_status in UserPrivacyStatus._ALL, f'Invalid privacy_status `{privacy_status}`'
        query_kwargs = {
            'Key': self.pk(user_id),
            'UpdateExpression': 'SET privacyStatus = :ps',
            'ExpressionAttributeValues': {':ps': privacy_status},
        }
        return self.client.update_item(query_kwargs)

    def set_user_details(self, user_id, full_name=None, bio=None, language_code=None, theme_code=None,
                         follow_counts_hidden=None, view_counts_hidden=None, email=None, phone=None,
                         comments_disabled=None, likes_disabled=None, sharing_disabled=None,
                         verification_hidden=None):
        "To ignore an attribute, leave it set to None. To delete an attribute, set it to the empty string."
        expression_actions = collections.defaultdict(list)
        expression_attribute_values = {}

        def process_attr(name, value):
            if value is not None:
                if value != '':
                    expression_actions['SET'].append(f'{name} = :{name}')
                    expression_attribute_values[f':{name}'] = value
                else:
                    expression_actions['REMOVE'].append(name)

        process_attr('fullName', full_name)
        process_attr('bio', bio)
        process_attr('languageCode', language_code)
        process_attr('themeCode', theme_code)
        process_attr('followCountsHidden', follow_counts_hidden)
        process_attr('viewCountsHidden', view_counts_hidden)
        process_attr('email', email)
        process_attr('phoneNumber', phone)
        process_attr('commentsDisabled', comments_disabled)
        process_attr('likesDisabled', likes_disabled)
        process_attr('sharingDisabled', sharing_disabled)
        process_attr('verificationHidden', verification_hidden)

        query_kwargs = {
            'Key': self.pk(user_id),
            'UpdateExpression': ' '.join([f'{k} {", ".join(v)}' for k, v in expression_actions.items()]),
        }
        if expression_attribute_values:
            query_kwargs['ExpressionAttributeValues'] = expression_attribute_values

        return self.client.update_item(query_kwargs)

    def set_user_accepted_eula_version(self, user_id, version):
        query_kwargs = {
            'Key': self.pk(user_id),
        }
        if version is None:
            query_kwargs['UpdateExpression'] = 'REMOVE acceptedEULAVersion'
        else:
            query_kwargs['UpdateExpression'] = 'SET acceptedEULAVersion = :aev'
            query_kwargs['ExpressionAttributeValues'] = {':aev': version}
        return self.client.update_item(query_kwargs)

    def _transact_increment_count(self, user_id, count_name):
        transact = {
            'Update': {
                'Key': self.typed_pk(user_id),
                'UpdateExpression': 'ADD #count_name :one',
                'ExpressionAttributeValues': {
                    ':one': {'N': '1'},
                },
                'ExpressionAttributeNames': {'#count_name': count_name},
                'ConditionExpression': 'attribute_exists(partitionKey)',  # only updates, no creates
            },
        }
        return transact

    def _transact_decrement_count(self, user_id, count_name):
        transact = {
            'Update': {
                'Key': self.typed_pk(user_id),
                'UpdateExpression': 'ADD #count_name :negative_one',
                # only updates, no creates and make sure it doesn't go negative
                'ConditionExpression': 'attribute_exists(#count_name) and #count_name > :zero',
                'ExpressionAttributeNames': {'#count_name': count_name},
                'ExpressionAttributeValues': {
                    ':negative_one': {'N': '-1'},
                    ':zero': {'N': '0'},
                },
            },
        }
        return transact

    def transact_increment_album_count(self, user_id):
        return self._transact_increment_count(user_id, 'albumCount')

    def transact_decrement_album_count(self, user_id):
        return self._transact_decrement_count(user_id, 'albumCount')

    def transact_increment_chat_count(self, user_id):
        return self._transact_increment_count(user_id, 'chatCount')

    def transact_decrement_chat_count(self, user_id):
        return self._transact_decrement_count(user_id, 'chatCount')

    def transact_increment_followed_count(self, user_id):
        return self._transact_increment_count(user_id, 'followedCount')

    def transact_decrement_followed_count(self, user_id):
        return self._transact_decrement_count(user_id, 'followedCount')

    def transact_increment_follower_count(self, user_id):
        return self._transact_increment_count(user_id, 'followerCount')

    def transact_decrement_follower_count(self, user_id):
        return self._transact_decrement_count(user_id, 'followerCount')

    def transact_increment_post_has_new_comment_activity_count(self, user_id):
        return self._transact_increment_count(user_id, 'postHasNewCommentActivityCount')

    def transact_decrement_post_has_new_comment_activity_count(self, user_id):
        return self._transact_decrement_count(user_id, 'postHasNewCommentActivityCount')

    def increment_post_viewed_by_count(self, user_id):
        query_kwargs = {
            'Key': self.pk(user_id),
            'UpdateExpression': 'ADD postViewedByCount :one',
            'ExpressionAttributeValues': {':one': 1},
        }
        try:
            return self.client.update_item(query_kwargs)
        except self.client.exceptions.ConditionalCheckFailedException:
            raise UserDoesNotExist(user_id)

    def transact_post_completed(self, user_id):
        kwargs = {
            'Key': self.typed_pk(user_id),
            'UpdateExpression': 'ADD postCount :positive_one',
            'ConditionExpression': 'attribute_exists(partitionKey)',
            'ExpressionAttributeValues': {
                ':positive_one': {'N': '1'},
            },
        }
        return {'Update': kwargs}

    def transact_post_archived(self, user_id, forced=False):
        kwargs = {
            'Key': self.typed_pk(user_id),
            'UpdateExpression': 'ADD postCount :negative_one, postArchivedCount :positive_one',
            'ConditionExpression': 'attribute_exists(partitionKey) and postCount > :zero',
            'ExpressionAttributeValues': {
                ':negative_one': {'N': '-1'},
                ':positive_one': {'N': '1'},
                ':zero': {'N': '0'},
            },
        }
        if forced:
            kwargs['UpdateExpression'] += ', postForcedArchivingCount :positive_one'
            kwargs['ExpressionAttributeValues'][':positive_one'] = {'N': '1'}
        return {'Update': kwargs}

    def transact_post_restored(self, user_id):
        kwargs = {
            'Key': self.typed_pk(user_id),
            'UpdateExpression': 'ADD postCount :positive_one, postArchivedCount :negative_one',
            'ConditionExpression': 'attribute_exists(partitionKey) and postArchivedCount > :zero',
            'ExpressionAttributeValues': {
                ':negative_one': {'N': '-1'},
                ':positive_one': {'N': '1'},
                ':zero': {'N': '0'},
            },
        }
        return {'Update': kwargs}

    def transact_post_deleted(self, user_id, prev_status):
        kwargs = {
            'Key': self.typed_pk(user_id),
            'UpdateExpression': 'ADD postDeletedCount :positive_one',
            'ConditionExpression': 'attribute_exists(partitionKey)',
            'ExpressionAttributeValues': {
                ':positive_one': {'N': '1'},
            },
        }
        count_to_decrement = {
            PostStatus.COMPLETED: 'postCount',
            PostStatus.ARCHIVED: 'postArchivedCount',
        }.get(prev_status)
        if count_to_decrement:
            kwargs['UpdateExpression'] += ', #ctd :negative_one'
            kwargs['ExpressionAttributeNames'] = {'#ctd': count_to_decrement}
            kwargs['ExpressionAttributeValues'][':negative_one'] = {'N': '-1'}
            kwargs['ExpressionAttributeValues'][':zero'] = {'N': '0'}
            kwargs['ConditionExpression'] += ' and #ctd > :zero'
        return {'Update': kwargs}

    def transact_comment_added(self, user_id):
        kwargs = {
            'Key': self.typed_pk(user_id),
            'UpdateExpression': 'ADD commentCount :positive_one',
            'ConditionExpression': 'attribute_exists(partitionKey)',
            'ExpressionAttributeValues': {
                ':positive_one': {'N': '1'},
            },
        }
        return {'Update': kwargs}

    def transact_comment_deleted(self, user_id, forced=False):
        kwargs = {
            'Key': self.typed_pk(user_id),
            'UpdateExpression': 'ADD commentCount :negative_one, commentDeletedCount :positive_one',
            'ConditionExpression': 'attribute_exists(partitionKey) AND commentCount > :zero',
            'ExpressionAttributeValues': {
                ':negative_one': {'N': '-1'},
                ':positive_one': {'N': '1'},
                ':zero': {'N': '0'},
            },
        }
        if forced:
            kwargs['UpdateExpression'] += ', commentForcedDeletionCount :positive_one'
            kwargs['ExpressionAttributeValues'][':positive_one'] = {'N': '1'}
        return {'Update': kwargs}
