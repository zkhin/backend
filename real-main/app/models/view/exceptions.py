class ViewException(Exception):
    pass


class ViewAlreadyExists(ViewException):

    def __init__(self, partition_key, user_id):
        self.partition_key = partition_key
        self.user_id = user_id

    def __str__(self):
        return f'View for `{self.partition_key}` by user `{self.user_id}` already exists'


class ViewDoesNotExist(ViewException):

    def __init__(self, partition_key, user_id):
        self.partition_key = partition_key
        self.user_id = user_id

    def __str__(self):
        return f'View for `{self.partition_key}` by user `{self.user_id}` does not exist'
