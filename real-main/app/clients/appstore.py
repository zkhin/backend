# https://developer.apple.com/documentation/appstorereceipts


class AppStoreClient:
    def __init__(self):
        # TODO: pass in password, product_id for diamond subscription
        self.url_production = 'https://buy.itunes.apple.com/verifyReceipt'
        self.url_sandbox = 'https://sandbox.itunes.apple.com/verifyReceipt'

    def verify_receipt(self, receipt_data_b64):
        # TODO:
        #   - call the endpoints, return the receipt status and latest_receipt_info
        #   - first call production verifyReceipt endpoint, and if that responds with a
        #     21007 status code, then call the sandbox endpoint
        status = 0
        latest_receipt_info = {}
        return status, latest_receipt_info
