import logging

from . import exceptions

logger = logging.getLogger()


class TrendingModelMixin:

    trending_exceptions = exceptions

    def __init__(self, trending_dynamo=None, **kwargs):
        super().__init__(**kwargs)
        if trending_dynamo:
            self.trending_dynamo = trending_dynamo

    def register_view(self):
        return self

    def deflate(self):
        return self
