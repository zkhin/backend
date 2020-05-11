import logging

logger = logging.getLogger()


class PostOriginalMetadataDynamo:

    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def get(self, post_id):
        return self.client.get_item({
            'partitionKey': f'post/{post_id}',
            'sortKey': 'originalMetadata',
        })

    def delete(self, post_id):
        return self.client.delete_item({
            'partitionKey': f'post/{post_id}',
            'sortKey': 'originalMetadata',
        })

    def transact_add(self, post_id, original_metadata):
        return {'Put': {
            'Item': {
                'schemaVersion': {'N': '0'},
                'partitionKey': {'S': f'post/{post_id}'},
                'sortKey': {'S': 'originalMetadata'},
                'originalMetadata': {'S': original_metadata},
            },
            'ConditionExpression': 'attribute_not_exists(partitionKey)',  # no updates, just adds
        }}
