import logging

from boto3.dynamodb.conditions import Key

logger = logging.getLogger()


class PostImageDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def get(self, post_id):
        return self.client.get_item({
            'partitionKey': f'post/{post_id}',
            'sortKey': 'image',
        })

    def transact_add(self, post_id, taken_in_real=None, original_format=None, image_format=None):
        item = {
            'schemaVersion': {'N': '0'},
            'partitionKey': {'S': f'post/{post_id}'},
            'sortKey': {'S': 'image'},
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

    def set_height_and_width(self, post_id, media_id, height, width):
        # if passed a media_id then our item is assumed to be a media item, else, it's a post_image
        pk = (
            {'partitionKey': f'media/{media_id}', 'sortKey': '-'} if media_id else
            {'partitionKey': f'post/{post_id}', 'sortKey': 'image'}
        )
        query_kwargs = {
            'Key': pk,
            'UpdateExpression': 'SET height = :height, width = :width',
            'ExpressionAttributeValues': {
                ':height': height,
                ':width': width,
            },
        }
        return self.client.update_item(query_kwargs)

    def set_colors(self, post_id, media_id, color_tuples):
        assert color_tuples, 'No support for deleting colors, yet'
        # if passed a media_id then our item is assumed to be a media item, else, it's a post_image
        pk = (
            {'partitionKey': f'media/{media_id}', 'sortKey': '-'} if media_id else
            {'partitionKey': f'post/{post_id}', 'sortKey': 'image'}
        )

        # transform to map before saving
        color_maps = [{
            'r': ct[0],
            'g': ct[1],
            'b': ct[2],
        } for ct in color_tuples]

        query_kwargs = {
            'Key': pk,
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
