import logging

from ..exceptions import AppStoreSubAlreadyExists

logger = logging.getLogger()


class AppStoreSubDynamo:
    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def pk(self, original_transaction_id):
        return {'partitionKey': f'appStoreSub/{original_transaction_id}', 'sortKey': '-'}

    def get(self, original_transaction_id, strongly_consistent=False):
        return self.client.get_item(self.pk(original_transaction_id), ConsistentRead=strongly_consistent)

    def add(
        self,
        original_transaction_id,
        original_purchase_at,
        expires_at,
        receipt_data_b64,
        latest_receipt_info,
        user_id,
    ):
        item = {
            **self.pk(original_transaction_id),
            'schemaVersion': 0,
            'userId': user_id,
            'receiptDataB64': receipt_data_b64,
            'latestReceiptInfo': latest_receipt_info,
            'gsiA1PartitionKey': f'appStoreSub/{user_id}',
            'gsiA1SortKey': original_purchase_at.to_iso8601_string(),
            'gsiK1PartitionKey': 'appStoreSub',
            'gsiK1SortKey': expires_at.to_iso8601_string(),
        }
        try:
            self.client.add_item({'Item': item})
        except self.client.exceptions.ConditionalCheckFailedException as err:
            raise AppStoreSubAlreadyExists(original_transaction_id) from err
        return item
