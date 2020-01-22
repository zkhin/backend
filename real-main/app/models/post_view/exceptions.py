class PostViewException(Exception):
    pass


class PostViewDoesNotExist(PostViewException):

    def __init__(self, post_id, viewed_by_user_id):
        self.post_id = post_id
        self.viewed_by_user_id = viewed_by_user_id

    def __str__(self):
        return f'PostView for post `{self.post_id}` and user `{self.viewed_by_user_id}` does not exist'


class PostViewAlreadyExists(PostViewException):

    def __init__(self, post_id, viewed_by_user_id):
        self.post_id = post_id
        self.viewed_by_user_id = viewed_by_user_id

    def __str__(self):
        return f'PostView for post `{self.post_id}` and user `{self.viewed_by_user_id}` already exists'
