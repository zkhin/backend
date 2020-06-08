import logging
from decimal import Decimal

import pendulum

from . import exceptions

logger = logging.getLogger()


class TrendingModelMixin:

    score_inflation_per_day = 2
    trending_exceptions = exceptions

    def __init__(self, trending_dynamo=None, **kwargs):
        super().__init__(**kwargs)
        if trending_dynamo:
            self.trending_dynamo = trending_dynamo

    @property
    def trending_item(self):
        this = self if hasattr(self, '_trending_item') else self.refresh_trending_item()
        return this._trending_item

    def refresh_trending_item(self, strongly_consistent=False):
        self._trending_item = self.trending_dynamo.get(self.id, strongly_consistent=strongly_consistent)
        return self

    def trending_increment_score(self, now=None, retry_count=0):
        if retry_count > 0:
            logger.warning(f'trending_increment_score() for item `{self.item_type}:{self.id}` retry {retry_count}')
        if retry_count > 2:
            raise Exception(
                f'trending_increment_score() failed for item `{self.item_type}:{self.id}` after {retry_count} tries'
            )
        now = now or pendulum.now('utc')
        last_deflated_at = pendulum.parse(self.trending_item['lastDeflatedAt']) if self.trending_item else now
        days_since_last_deflation = (now - last_deflated_at.start_of('day')).total_days()
        inflated_score = Decimal(self.score_inflation_per_day ** days_since_last_deflation)

        if self.trending_item:
            try:
                self._trending_item = self.trending_dynamo.add_score(self.id, inflated_score, last_deflated_at)
            except exceptions.TrendingDNEOrAttributeMismatch:
                pass
            else:
                return self
        else:
            try:
                self._trending_item = self.trending_dynamo.add(self.id, inflated_score, now=now)
            except exceptions.TrendingAlreadyExists:
                pass
            else:
                return self

        # we lost a race condition, try again.
        self.refresh_trending_item(strongly_consistent=True)
        return self.trending_increment_score(now=now, retry_count=retry_count + 1)

    def trending_delete(self):
        self._trending_item = self.trending_dynamo.delete(self.id)
        return self
