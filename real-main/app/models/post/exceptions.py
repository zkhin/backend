class PostException(Exception):
    pass


class PostDoesNotExist(PostException):

    def __init__(self, post_id):
        self.post_id = post_id

    def __str__(self):
        return f'Post `{self.post_id}` does not exist'


class DuplicatePost(PostException):

    def __init__(self, post_id=None):
        self.post_id = post_id

    def __str__(self):
        return f'Post `{self.post_id}` duplicated' if self.post_id else 'Duplicate post encountered'


class AlreadyFlagged(PostException):

    def __init__(self, post_id, user_id):
        self.post_id = post_id
        self.user_id = user_id
        super().__init__()

    def __str__(self):
        return f'Post `{self.post_id}` has already been flagged by user `{self.user_id}`'


class NotFlagged(PostException):

    def __init__(self, post_id, user_id):
        self.post_id = post_id
        self.user_id = user_id
        super().__init__()

    def __str__(self):
        return f'Post `{self.post_id}` has not been flagged by user `{self.user_id}`'


class UnableToDecrementPostLikeCounter(PostException):

    def __init__(self, post_id):
        self.post_id = post_id
        super().__init__()

    def __str__(self):
        return f'Post `{self.post_id}` either does not exist or has a like counter of < 1'


class DoesNotHaveExpectedCommentActivity(PostException):

    def __init__(self, post_id, expected_value):
        self.post_id = post_id
        self.expected_value = expected_value

    def __str__(self):
        return f'Post `{self.post_id}` does not have Post.hasNewCommentActivity set to `{self.expected_value}`'
