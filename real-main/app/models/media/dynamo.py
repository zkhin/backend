from datetime import datetime
from functools import reduce
import logging

from boto3.dynamodb.conditions import Attr, Key

from app.lib import datetime as real_datetime

from .enums import MediaStatus

logger = logging.getLogger()


class MediaDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def get_media(self, media_id, strongly_consistent=False):
        return self.client.get_item({
            'partitionKey': f'media/{media_id}',
            'sortKey': '-',
        }, strongly_consistent=strongly_consistent)

    def transact_add_media(self, posted_by_user_id, post_id, media_id, media_type, posted_at=None,
                           taken_in_real=None, original_format=None):
        posted_at_str = real_datetime.serialize(posted_at or datetime.utcnow())
        media_item = {
            'schemaVersion': {'N': '0'},
            'partitionKey': {'S': f'media/{media_id}'},
            'sortKey': {'S': '-'},
            'gsiA1PartitionKey': {'S': f'media/{post_id}'},
            'gsiA1SortKey': {'S': MediaStatus.AWAITING_UPLOAD},
            'gsiA2PartitionKey': {'S': f'media/{posted_by_user_id}'},
            'gsiA2SortKey': {'S': f'{media_type}/{MediaStatus.AWAITING_UPLOAD}/{posted_at_str}'},
            'userId': {'S': posted_by_user_id},
            'postId': {'S': post_id},
            'postedAt': {'S': posted_at_str},
            'mediaId': {'S': media_id},
            'mediaType': {'S': media_type},
            'mediaStatus': {'S': MediaStatus.AWAITING_UPLOAD},
        }
        if taken_in_real is not None:
            media_item['takenInReal'] = {'BOOL': taken_in_real}
        if original_format is not None:
            media_item['originalFormat'] = {'S': original_format}
        return {'Put': {
            'Item': media_item,
            'ConditionExpression': 'attribute_not_exists(partitionKey)',  # no updates, just adds
        }}

    def set_is_verified(self, media_id, is_verified):
        query_kwargs = {
            'Key': {
                'partitionKey': f'media/{media_id}',
                'sortKey': '-',
            },
            'UpdateExpression': 'SET isVerified = :iv',
            'ExpressionAttributeValues': {':iv': is_verified},
        }
        return self.client.update_item(query_kwargs)

    def set_height_and_width(self, media_id, height, width):
        query_kwargs = {
            'Key': {
                'partitionKey': f'media/{media_id}',
                'sortKey': '-',
            },
            'UpdateExpression': 'SET height = :height, width = :width',
            'ExpressionAttributeValues': {
                ':height': height,
                ':width': width,
            },
        }
        return self.client.update_item(query_kwargs)

    def transact_set_status(self, media_item, status):
        return {
            'Update': {
                'Key': {
                    'partitionKey': {'S': f'media/{media_item["mediaId"]}'},
                    'sortKey': {'S': '-'},
                },
                'UpdateExpression': f'SET mediaStatus = :status, gsiA1SortKey = :status, gsiA2SortKey = :gsiA2SK',
                'ExpressionAttributeValues': {
                    ':status': {'S': status},
                    ':gsiA2SK': {'S': f'{media_item["mediaType"]}/{status}/{media_item["postedAt"]}'},
                },
                'ConditionExpression': 'attribute_exists(partitionKey)',  # only updates, no creates
            }
        }

    def generate_by_user(self, user_id):
        query_kwargs = {
            'KeyConditionExpression': Key('gsiA2PartitionKey').eq(f'media/{user_id}'),
            'IndexName': 'GSI-A2',
        }
        return self.client.generate_all_query(query_kwargs)

    def generate_by_post(self, post_id, uploaded=None):
        key_exps = [Key('gsiA1PartitionKey').eq(f'media/{post_id}')]
        if uploaded is True:
            key_exps.append(Key('gsiA1SortKey').eq(MediaStatus.UPLOADED))

        query_kwargs = {
            'KeyConditionExpression': reduce(lambda a, b: a & b, key_exps),
            'IndexName': 'GSI-A1',
        }

        if uploaded is False:
            query_kwargs['FilterExpression'] = Attr('mediaStatus').ne(MediaStatus.UPLOADED)

        return self.client.generate_all_query(query_kwargs)
