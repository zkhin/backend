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


class UnableToDecrementPostLikeCounter(PostException):
    def __init__(self, post_id):
        self.post_id = post_id
        super().__init__()

    def __str__(self):
        return f'Post `{self.post_id}` either does not exist or has a like counter of < 1'


generic = PostException
dne = PostDoesNotExist
