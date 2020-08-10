import logging

logger = logging.getLogger()


class UserContactAttributeDynamo:

    schema_version = 0

    def __init__(self, dynamo_client, pk_prefix):
        self.pk_prefix = pk_prefix
        self.client = dynamo_client

    def key(self, attr):
        return {'partitionKey': f'{self.pk_prefix}/{attr}', 'sortKey': '-'}

    def get(self, attr, strongly_consistent=False):
        return self.client.get_item(self.key(attr), ConsistentRead=strongly_consistent)

    def add(self, attr, user_id):
        item = {
            **self.key(attr),
            'schemaVersion': self.schema_version,
            'userId': user_id,
        }
        return self.client.add_item({'Item': item})

    def delete(self, attr, user_id):
        kwargs = {
            'Key': self.key(attr),
            'ConditionExpression': 'attribute_not_exists(userId) OR userId = :uid',
            'ExpressionAttributeValues': {':uid': user_id},
            'ReturnValues': 'ALL_OLD',
        }
        return self.client.table.delete_item(**kwargs).get('Attributes') or None
