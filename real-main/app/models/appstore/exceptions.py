class AppStoreException(Exception):
    pass


class AppStoreReceiptAlreadyExists(AppStoreException):
    def __init__(self, receipt_data_b64_md5):
        self.receipt_data_b64_md5 = receipt_data_b64_md5

    def __str__(self):
        return f'AppStore receipt with md5 of b64 data of `{self.receipt_data_b64_md5}` already exists'


class AppStoreSubAlreadyExists(AppStoreException):
    def __init__(self, original_transaction_id):
        self.original_transaction_id = original_transaction_id

    def __str__(self):
        return f'AppStore sub with original transaction ID of `{self.original_transaction_id}` already exists'
