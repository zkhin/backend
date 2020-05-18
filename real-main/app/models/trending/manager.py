import decimal
import logging
import math

import pendulum

from app import models

from . import dynamo, enums, exceptions

logger = logging.getLogger()


class TrendingManager:

    enums = enums
    exceptions = exceptions

    lifetime_days = 1
    lifetime = pendulum.duration(days=lifetime_days)
    min_score_cutoff = lifetime_days / math.e

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['trending'] = self
        self.post_manager = managers.get('post') or models.PostManager(clients, managers=managers)
        self.user_manager = managers.get('user') or models.UserManager(clients, managers=managers)

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = dynamo.TrendingDynamo(clients['dynamo'])

    def increment_scores_for_post(self, post, now=None):
        now = now or pendulum.now('utc')

        # Non-original posts don't contribute to trending
        if post.id != post.item.get('originalPostId', post.id):
            return

        # don't add the trending indexes if the post is more than a 24 hrs old
        if (now - post.posted_at > pendulum.duration(hours=24)):
            return

        # don't add posts that failed verification
        if post.item.get('isVerified') is False:
            return

        # don't add real user or their posts to trending indexes
        if post.user_id == self.user_manager.real_user_id:
            return

        self.increment_score(enums.TrendingItemType.POST, post.id, now=now)
        self.increment_score(enums.TrendingItemType.USER, post.user_id, now=now)

    def increment_score(self, item_type, item_id, amount=1, now=None):
        now = now or pendulum.now('utc')
        # first try to add it to an existing item
        try:
            return self.dynamo.increment_trending_pending_view_count(item_id, amount, now=now)
        except self.exceptions.TrendingException:
            pass

        # try to add a new item
        try:
            return self.dynamo.create_trending(item_type, item_id, amount, now=now)
        except self.exceptions.TrendingAlreadyExists:
            pass

        # try to add it to an existing item with the same 'now' as this view
        # this happens when a user views multiple posts by the same user for the first time
        try:
            return self.dynamo.increment_trending_score(item_id, amount, now=now)
        except self.exceptions.TrendingException:
            pass

        # we should get here in the case of a race condition which we lost.
        # as such, we should now be able to add it to an existing item
        return self.dynamo.increment_trending_pending_view_count(item_id, amount, now=now)

    def reindex(self, item_type, cutoff=None):
        "Do a pass over all trending items of `item_type` and update their score"
        cutoff = cutoff or pendulum.now('utc')
        for item in self.dynamo.generate_trendings(item_type, max_last_indexed_at=cutoff):
            item_id = item['partitionKey'][9:]
            old_score = item['gsiK3SortKey']
            last_indexed_at = pendulum.parse(item['gsiA1SortKey'])
            pending_view_count = item['pendingViewCount']
            new_score = self.calculate_new_score(old_score, last_indexed_at, pending_view_count, cutoff)

            # avoiding maintain an long tail of trending items
            if new_score < self.min_score_cutoff:
                self.dynamo.delete_trending(item_id)
            else:
                self.dynamo.update_trending_score(item_id, new_score, cutoff, last_indexed_at, pending_view_count)

    def calculate_new_score(self, old_score, last_indexed_at, pending_view_count, now):
        "Calcualte the new score for the item, as a Decimal, because that's what dynamodb can consume"
        coeff = decimal.Decimal(math.exp((now - last_indexed_at) / self.lifetime) ** -1)
        return old_score * coeff + pending_view_count
