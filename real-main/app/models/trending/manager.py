from datetime import datetime, timedelta
from decimal import Decimal
import logging
import math

from app.lib import datetime as real_datetime

from . import dynamo, enums, exceptions

logger = logging.getLogger()


class TrendingManager:

    enums = enums
    exceptions = exceptions

    average_lifetime = timedelta(days=1)
    min_score_cutoff = 0.37  # ~ 1/e

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['trending'] = self

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = dynamo.TrendingDynamo(clients['dynamo'])

    def record_view_count(self, item_type, item_id, view_count, now=None):
        now = now or datetime.utcnow()
        # first try to add it to an existing item
        try:
            return self.dynamo.increment_trending_pending_view_count(item_id, view_count)
        except self.exceptions.TrendingDoesNotExist:
            pass

        # try to add a new item
        try:
            return self.dynamo.create_trending(item_type, item_id, view_count, now=now)
        except self.exceptions.TrendingAlreadyExists:
            pass

        # we should get here in the case of a race condition which we lost.
        # as such, we should now be able to add it to an existing item
        return self.dynamo.increment_trending_pending_view_count(item_id, view_count)

    def reindex(self, item_type, cutoff=None):
        "Do a pass over all trending items of `item_type` and update their score"
        cutoff = cutoff or datetime.utcnow()
        for item in self.dynamo.generate_trendings(item_type, max_last_indexed_at=cutoff):
            item_id = item['partitionKey'][9:]
            old_score = item['gsiK3SortKey']
            last_indexed_at = real_datetime.parse(item['gsiA1SortKey'])
            pending_view_count = item['pendingViewCount']
            new_score = self.calculate_new_score(old_score, last_indexed_at, pending_view_count, cutoff)

            # avoiding maintain an long tail of trending items
            if new_score < self.min_score_cutoff:
                self.dynamo.delete_trending(item_id)
            else:
                self.dynamo.update_trending_score(item_id, new_score, cutoff, last_indexed_at, pending_view_count)

    def calculate_new_score(self, old_score, last_indexed_at, pending_view_count, now):
        "Calcualte the new score for the item, as a Decimal, because that's what dynamodb can consume"
        coeff = Decimal(math.exp((now - last_indexed_at) / self.average_lifetime) ** -1)
        return old_score * coeff + pending_view_count
