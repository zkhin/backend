class FlagException(Exception):
    pass


class AlreadyFlagged(FlagException):

    def __init__(self, item_type, item_id, user_id):
        super().__init__()
        self.item_type = item_type
        self.item_id = item_id
        self.user_id = user_id

    def __str__(self):
        return f'{self.item_type.capitalize()} `{self.item_id}` has already been flagged by user `{self.user_id}`'


class NotFlagged(FlagException):

    def __init__(self, item_type, item_id, user_id):
        super().__init__()
        self.item_type = item_type
        self.item_id = item_id
        self.user_id = user_id

    def __str__(self):
        return f'{self.item_type.capitalize()} `{self.item_id}` has not been flagged by user `{self.user_id}`'
