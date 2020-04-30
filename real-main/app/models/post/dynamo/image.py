import logging

from boto3.dynamodb.conditions import Key
import pendulum

logger = logging.getLogger()


class PostImageDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def get(self, media_id):
        return self.client.get_item({
            'partitionKey': f'media/{media_id}',
            'sortKey': '-',
        })

    def transact_add(self, posted_by_user_id, post_id, media_id, posted_at=None, taken_in_real=None,
                     original_format=None, image_format=None):
        posted_at = posted_at or pendulum.now('utc')
        posted_at_str = posted_at.to_iso8601_string()
        item = {
            'schemaVersion': {'N': '2'},
            'partitionKey': {'S': f'media/{media_id}'},
            'sortKey': {'S': '-'},
            'gsiA1PartitionKey': {'S': f'media/{post_id}'},
            'gsiA1SortKey': {'S': '-'},
            'userId': {'S': posted_by_user_id},
            'postId': {'S': post_id},
            'postedAt': {'S': posted_at_str},
            'mediaId': {'S': media_id},
            'mediaType': {'S': 'IMAGE'},
        }
        if taken_in_real is not None:
            item['takenInReal'] = {'BOOL': taken_in_real}
        if original_format is not None:
            item['originalFormat'] = {'S': original_format}
        if image_format is not None:
            item['imageFormat'] = {'S': image_format}
        return {'Put': {
            'Item': item,
            'ConditionExpression': 'attribute_not_exists(partitionKey)',  # no updates, just adds
        }}

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

    def set_colors(self, media_id, color_tuples):
        assert color_tuples, 'No support for deleting colors, yet'

        # transform to map before saving
        color_maps = [{
            'r': ct[0],
            'g': ct[1],
            'b': ct[2],
        } for ct in color_tuples]

        query_kwargs = {
            'Key': {
                'partitionKey': f'media/{media_id}',
                'sortKey': '-',
            },
            'UpdateExpression': 'SET colors = :colors',
            'ExpressionAttributeValues': {':colors': color_maps},
        }
        return self.client.update_item(query_kwargs)

    def generate_by_post(self, post_id):
        query_kwargs = {
            'KeyConditionExpression': Key('gsiA1PartitionKey').eq(f'media/{post_id}'),
            'IndexName': 'GSI-A1',
        }
        return self.client.generate_all_query(query_kwargs)
