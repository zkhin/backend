class AppStoreException(Exception):
    pass


class AppStoreSubAlreadyExists(AppStoreException):
    def __init__(self, original_transaction_id):
        self.original_transaction_id = original_transaction_id

    def __str__(self):
        return f'AppStore sub with original transaction ID of `{self.original_transaction_id}` already exists'


class AppStoreTransactionAlreadyExists(AppStoreException):
    def __init__(self, transaction_id):
        self.transaction_id = transaction_id

    def __str__(self):
        return f'AppStore transaction with transaction ID of `{self.transaction_id}` already exists'
