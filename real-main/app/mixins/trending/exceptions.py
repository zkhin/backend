class TrendingException(Exception):
    pass


class TrendingAlreadyExists(TrendingException):
    def __init__(self, item_type, item_id):
        self.item_type = item_type
        self.item_id = item_id

    def __str__(self):
        return f'Trending for `{self.item_type}:{self.item_id}` already exists'


class TrendingDNEOrLastDeflatedAtMismatch(TrendingException):
    def __init__(self, item_type, item_id):
        self.item_type = item_type
        self.item_id = item_id

    def __str__(self):
        return f'Trending for `{self.item_type}:{self.item_id}` does not exist or has different lastDeflatedAt'


class TrendingDNEOrScoreMismatch(TrendingException):
    def __init__(self, item_type, item_id):
        self.item_type = item_type
        self.item_id = item_id

    def __str__(self):
        return f'Trending for `{self.item_type}:{self.item_id}` does not exist or has different score'
