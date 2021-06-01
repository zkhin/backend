import logging

import pendulum

from app import models
from app.models.post.enums import AdStatus

from .dynamo import AdFeedDynamo

logger = logging.getLogger()


class AdFeedManager:
    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['ad_feed'] = self
        self.post_manager = managers.get('post') or models.PostManager(clients, managers=managers)
        self.user_manager = managers.get('user') or models.UserManager(clients, managers=managers)
        self.clients = clients
        if 'dynamo_ad_feed' in clients:
            self.dynamo = AdFeedDynamo(clients['dynamo_ad_feed'])
        if 'real_transactions' in clients:
            self.real_transactions_client = clients['real_transactions']

    def on_ad_post_ad_status_change(self, post_id, new_item, old_item=None):
        old_ad_status = (old_item or {}).get('adStatus', AdStatus.NOT_AD)
        new_ad_status = new_item.get('adStatus', AdStatus.NOT_AD)
        assert old_ad_status != new_ad_status, 'Should only be called when adStatus changes'
        posted_by_user_id = new_item['postedByUserId']
        if old_ad_status != AdStatus.ACTIVE and new_ad_status == AdStatus.ACTIVE:
            user_id_generator = self.user_manager.dynamo.generate_user_ids_by_ads_disabled(
                False, exclude_user_id=posted_by_user_id
            )
            self.dynamo.add_ad_post_for_users(post_id, user_id_generator)
        if old_ad_status == AdStatus.ACTIVE and new_ad_status != AdStatus.ACTIVE:
            self.dynamo.delete_by_post(post_id)

    def on_post_view_last_viewed_at_change(self, post_id, new_item, old_item=None):
        old_lva = (old_item or {}).get('lastViewedAt')
        new_lva = new_item.get('lastViewedAt')
        assert old_lva != new_lva, 'Should only be called when lastViewedAt changes'
        post = self.post_manager.get_post(post_id)
        if post.ad_status == AdStatus.ACTIVE:
            user_id = new_item['sortKey'].split('/')[1]
            self.dynamo.set_last_viewed_at(post_id, user_id, new_lva)

    def on_post_view_focus_last_viewed_at_change(self, post_id, new_item, old_item=None):
        old_lva_str = (old_item or {}).get('focusLastViewedAt')
        new_lva_str = new_item.get('focusLastViewedAt')
        assert old_lva_str != new_lva_str, 'Should only be called when focusLastViewedAt changes'
        user_id = new_item['sortKey'].split('/')[1]
        post = self.post_manager.get_post(post_id)
        ad_payment = post.item.get('adPayment')
        if post.ad_status != AdStatus.ACTIVE or post.user_id == user_id or not ad_payment:
            return
        new_lva = pendulum.parse(new_lva_str)
        ad_feed_item = self.dynamo.get(post_id, user_id)
        ad_payment_period, prev_lva = [
            pendulum.parse(item[name]) if name in item else None
            for name, item in [['adPaymentPeriod', post.item], ['lastPaymentForViewAt', ad_feed_item]]
        ]
        if prev_lva and (not ad_payment_period or new_lva - prev_lva < ad_payment_period):
            return
        # upon losing a race condition, first dynamo write will throw an error, upon which the dynamo
        # tream processor will re-run us, and we should see the updated data in dynamo
        self.dynamo.record_payment_start(post_id, user_id, new_lva, prev_lva)
        self.real_transactions_client.pay_for_ad_view(user_id, post.user_id, post.id, ad_payment)
        self.dynamo.record_payment_finish(post_id, user_id)

    def on_user_ads_disabled_change(self, user_id, new_item, old_item=None):
        old_ads_disabled = (old_item or {}).get('adsDisabled', False)
        new_ads_disabled = new_item.get('adsDisabled', False)
        assert old_ads_disabled != new_ads_disabled, 'Should only be called when adsDisabled changes'
        if not old_ads_disabled and new_ads_disabled:
            self.dynamo.delete_by_user(user_id)
        if old_ads_disabled and not new_ads_disabled:
            post_id_generator = self.post_manager.dynamo.generate_post_ids_by_ad_status(
                AdStatus.ACTIVE, exclude_posted_by_user_id=user_id
            )
            self.dynamo.add_ad_posts_for_user(user_id, post_id_generator)

    def on_user_delete(self, user_id, old_item):
        self.dynamo.delete_by_user(user_id)
