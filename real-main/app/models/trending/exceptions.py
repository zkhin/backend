class TrendingException(Exception):
    pass


class TrendingDoesNotExist(TrendingException):

    def __init__(self, item_id):
        self.item_id = item_id

    def __str__(self):
        return f'No trending exists for item id `{self.item_id}`'


class TrendingAlreadyExists(TrendingException):

    def __init__(self, item_id):
        self.item_id = item_id

    def __str__(self):
        return f'trending item already exists for item id `{self.item_id}`'
