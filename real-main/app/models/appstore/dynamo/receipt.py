import logging

import pendulum

from ..exceptions import AppStoreReceiptAlreadyExists

logger = logging.getLogger()


class AppStoreReceiptDynamo:
    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def pk(self, receipt_data_b64_md5):
        return {'partitionKey': f'appStoreReceipt/{receipt_data_b64_md5}', 'sortKey': '-'}

    def get(self, receipt_data_b64_md5, strongly_consistent=False):
        return self.client.get_item(self.pk(receipt_data_b64_md5), ConsistentRead=strongly_consistent)

    def add(self, receipt_data_b64_md5, receipt_data_b64, user_id):
        item = {
            **self.pk(receipt_data_b64_md5),
            'schemaVersion': 0,
            'userId': user_id,
            'receiptDataB64': receipt_data_b64,
            'receiptDataB64MD5': receipt_data_b64_md5,
            'gsiA1PartitionKey': f'appStoreReceipt/{user_id}',
            'gsiA1SortKey': '-',
        }
        try:
            self.client.add_item({'Item': item})
        except self.client.exceptions.ConditionalCheckFailedException as err:
            raise AppStoreReceiptAlreadyExists(receipt_data_b64_md5) from err
        return item

    def add_verification_attempt(self, key, status_code, at, next_at=None, first=False):
        query_kwargs = {
            'Key': key,
            'UpdateExpression': (
                'ADD #vac :one SET #vala = :at, #vasc = list_append(if_not_exists(#vasc, :emptyList), :scl)'
            ),
            'ExpressionAttributeNames': {
                '#vala': 'verifyAttemptsLastAt',
                '#vasc': 'verifyAttemptsStatusCodes',
                '#vac': 'verifyAttemptsCount',
            },
            'ExpressionAttributeValues': {
                ':at': at.to_iso8601_string(),
                ':one': 1,
                ':scl': [status_code],
                ':emptyList': [],
            },
        }
        if next_at:
            query_kwargs['UpdateExpression'] += ', gsiK1PartitionKey = :pk, gsiK1SortKey = :sk'
            query_kwargs['ExpressionAttributeValues'][':pk'] = 'appStoreReceipt'
            query_kwargs['ExpressionAttributeValues'][':sk'] = next_at.to_iso8601_string()
        if first:
            query_kwargs['UpdateExpression'] += ', #vafa = :at'
            query_kwargs['ExpressionAttributeNames']['#vafa'] = 'verifyAttemptsFirstAt'
        return self.client.update_item(
            query_kwargs, failure_warning=f'Failed to set last verification attempt for apple receipt `{key}`'
        )

    def generate_keys_to_verify(self, now=None):
        now = now or pendulum.now('utc')
        query_kwargs = {
            'KeyConditionExpression': 'gsiK1PartitionKey = :pk AND gsiK1SortKey <= :sk_max',
            'ExpressionAttributeValues': {':pk': 'appStoreReceipt', ':sk_max': now.to_iso8601_string()},
            'ProjectionExpression': 'partitionKey, sortKey',
            'IndexName': 'GSI-K1',
        }
        return self.client.generate_all_query(query_kwargs)

    def generate_keys_by_user(self, user_id):
        query_kwargs = {
            'KeyConditionExpression': 'gsiA1PartitionKey = :pk',
            'ExpressionAttributeValues': {':pk': f'appStoreReceipt/{user_id}'},
            'ProjectionExpression': 'partitionKey, sortKey',
            'IndexName': 'GSI-A1',
        }
        return self.client.generate_all_query(query_kwargs)
