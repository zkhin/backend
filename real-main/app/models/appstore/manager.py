import hashlib
import logging

from .dynamo import AppStoreReceiptDynamo, AppStoreSubDynamo

logger = logging.getLogger()


class AppStoreManager:
    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['appstore'] = self

        self.clients = clients
        if 'appstore' in clients:
            self.appstore_client = self.clients['appstore']
        if 'dynamo' in clients:
            self.receipt_dynamo = AppStoreReceiptDynamo(clients['dynamo'])
            self.sub_dynamo = AppStoreSubDynamo(clients['dynamo'])

    def add_receipt(self, receipt_data_b64, user_id):
        receipt_data_b64_md5 = hashlib.md5(receipt_data_b64.encode('utf-8')).hexdigest()
        self.receipt_dynamo.add(receipt_data_b64_md5, receipt_data_b64, user_id)

    def verify_receipts(self, now=None):
        """
        Attempt to verify receipts that have failed verification with temporary failures.
        Returns counts of how many verifications where attempted and how many succeeded.
        """
        # TODO:
        #   - iterate through all receipts queued to be verified, for each
        #       - use the app store client to call the verifyReceipt endpoint
        #       - depending on the payload returned, either create an apple subscription, queue
        #         the receipt for another verification attempt or fail permenantly and send out an error alert

    def on_receipt_add_verify(self, receipt_data_b64_md5, new_item):
        # status, latest_receipt_info = self.appstore_client.verify_receipt(new_item['receiptDataB64'])
        # TODO:
        #   - use the app store client to call the verifyReceipt endpoint
        #   - depending on the payload returned, either create an apple subscription, queue
        #     the receipt for another verification attempt or fail permenantly and send out an error alert
        pass

    def on_user_delete_delete_receipts(self, user_id, old_item):
        key_generator = self.receipt_dynamo.generate_keys_by_user(user_id)
        self.receipt_dynamo.client.batch_delete_items(key_generator)
