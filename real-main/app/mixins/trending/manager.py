import logging

import pendulum

from . import exceptions
from .dynamo import TrendingDynamo

logger = logging.getLogger()


class TrendingManagerMixin:

    score_inflation_per_day = 2
    trending_exceptions = exceptions

    min_count_to_keep = 10 * 1000
    min_score_to_keep = 0.5

    def __init__(self, clients, managers=None):
        super().__init__(clients, managers=managers)
        if 'dynamo' in clients:
            self.trending_dynamo = TrendingDynamo(self.item_type, clients['dynamo'])

    def trending_deflate(self, now=None):
        """
        Iterate over all trending items and deflate them.
        Returns a pair of integers: (total_items, deflated_items)
        """
        now = now or pendulum.now('utc')
        # iterates from lowest score upward, deflate and count each one
        total_count, deflated_count = 0, 0
        for trending_keys in self.trending_dynamo.generate_keys():
            deflated = self.trending_deflate_item(trending_keys, now=now)
            deflated_count += int(deflated)
            total_count += 1
        return total_count, deflated_count

    def trending_deflate_item(self, trending_item, now=None, retry_count=0):
        """
        Deflate a single trending item. Can accept a full trending_item or just the keys from PK & GSI-K3.

        When operating on just the trending_keys, will assume that we are on a once-per-day deflation schedule.
        If that's not the case, our first write to dynamo to deflate the score write will fail.
        We will then pull the full trending item from the DB (thus getting the correct lastDeflatedAt) and
        recurse on this method to deflate the score.
        """
        item_id = trending_item['partitionKey'].split('/')[1]
        if retry_count > 2:
            raise Exception(
                f'trending_deflate_item() failed for item `{self.item_type}:{item_id}` after {retry_count} tries'
            )

        now = now or pendulum.now('utc')
        last_deflation_at = (
            pendulum.parse(trending_item['lastDeflatedAt'])
            if 'lastDeflatedAt' in trending_item
            else now.subtract(days=1)  # common case, dynamo write will fail if we're wrong
        )
        days_since_last_deflation = (now - last_deflation_at.start_of('day')).days
        if days_since_last_deflation < 1:
            logging.warning(f'Trending for item `{self.item_type}:{item_id}` has already been deflated today')
            return False

        current_score = trending_item['gsiK3SortKey']
        new_score = current_score / (self.score_inflation_per_day ** days_since_last_deflation)

        try:
            self.trending_dynamo.deflate_score(item_id, current_score, new_score, last_deflation_at.date(), now)
        except exceptions.TrendingDNEOrAttributeMismatch:
            logging.warning(
                f'Trending deflate (common case assumption?) failure, trying again for `{self.item_type}:{item_id}`'
            )
            trending_item = self.trending_dynamo.get(item_id, strongly_consistent=True)
            return self.trending_deflate_item(trending_item, now=now, retry_count=retry_count + 1)
        return True

    def trending_delete_tail(self, total_count):
        max_to_delete = total_count - self.min_count_to_keep
        if max_to_delete <= 0:
            return 0

        deleted = 0
        for trending_keys in self.trending_dynamo.generate_keys():
            item_id = trending_keys['partitionKey'].split('/')[1]
            current_score = trending_keys['gsiK3SortKey']
            if current_score >= self.min_score_to_keep:
                break
            try:
                self.trending_dynamo.delete(item_id, expected_score=current_score)
            except exceptions.TrendingDNEOrAttributeMismatch:
                # race condition, the item must have recieved a boost in score
                logging.warning(f'Lost race condition, not deleting trending for `{self.item_type}:{item_id}`')
            else:
                deleted += 1
            if deleted >= max_to_delete:
                break

        return deleted
