import logging

logger = logging.getLogger()


class PostImageDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def get(self, post_id, strongly_consistent=False):
        return self.client.get_item({
            'partitionKey': f'post/{post_id}',
            'sortKey': 'image',
        }, strongly_consistent=strongly_consistent)

    def delete(self, post_id):
        query_kwargs = {'Key': {
            'partitionKey': f'post/{post_id}',
            'sortKey': 'image',
        }}
        return self.client.delete_item(query_kwargs)

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

    def set_height_and_width(self, post_id, height, width):
        query_kwargs = {
            'Key': {'partitionKey': f'post/{post_id}', 'sortKey': 'image'},
            'UpdateExpression': 'SET height = :height, width = :width',
            'ExpressionAttributeValues': {
                ':height': height,
                ':width': width,
            },
        }
        return self.client.update_item(query_kwargs)

    def set_colors(self, post_id, color_tuples):
        assert color_tuples, 'No support for deleting colors, yet'

        # transform to map before saving
        color_maps = [{
            'r': ct[0],
            'g': ct[1],
            'b': ct[2],
        } for ct in color_tuples]

        query_kwargs = {
            'Key': {'partitionKey': f'post/{post_id}', 'sortKey': 'image'},
            'UpdateExpression': 'SET colors = :colors',
            'ExpressionAttributeValues': {':colors': color_maps},
        }
        return self.client.update_item(query_kwargs)
