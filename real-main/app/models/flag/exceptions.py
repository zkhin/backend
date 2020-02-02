class FlagException(Exception):
    pass


class AlreadyFlagged(FlagException):

    def __init__(self, post_id, user_id):
        self.post_id = post_id
        self.user_id = user_id
        super().__init__()

    def __str__(self):
        return f'Post `{self.post_id}` has already been flagged by user `{self.user_id}`'


class NotFlagged(FlagException):

    def __init__(self, post_id, user_id):
        self.post_id = post_id
        self.user_id = user_id
        super().__init__()

    def __str__(self):
        return f'Post `{self.post_id}` has not been flagged by user `{self.user_id}`'
