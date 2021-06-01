from decimal import Decimal
from unittest.mock import call, patch
from uuid import uuid4

import pendulum
import pytest

from app.models.post.enums import AdStatus


def test_on_ad_post_ad_status_change_throws_if_not_changed(ad_feed_manager):
    post_id = str(uuid4())
    item = {'postId': post_id, 'adStatus': str(uuid4())}
    with pytest.raises(AssertionError, match=' adStatus '):
        ad_feed_manager.on_ad_post_ad_status_change(post_id, new_item=item, old_item=item)

    old_item = {'postId': post_id}
    new_item = {**old_item, 'adStatus': AdStatus.NOT_AD}
    with pytest.raises(AssertionError, match=' adStatus '):
        ad_feed_manager.on_ad_post_ad_status_change(post_id, new_item=new_item, old_item=old_item)


def test_on_ad_post_ad_status_change_noop_if_not_to_or_from_ACTIVE(ad_feed_manager):
    user_id, post_id = str(uuid4()), str(uuid4())
    new_item = {'postId': post_id, 'postedByUserId': user_id, 'adStatus': str(uuid4())}
    old_item = {'postId': post_id, 'postedByUserId': user_id, 'adStatus': str(uuid4())}
    with patch.object(ad_feed_manager, 'dynamo') as dynamo_mock:
        ad_feed_manager.on_ad_post_ad_status_change(post_id, new_item=new_item, old_item=old_item)
    assert dynamo_mock.mock_calls == []


def test_on_ad_post_ad_status_change_to_active(ad_feed_manager):
    user_id, post_id = str(uuid4()), str(uuid4())
    new_item = {'postId': post_id, 'postedByUserId': user_id, 'adStatus': AdStatus.ACTIVE}
    old_item = {'postId': post_id, 'postedByUserId': user_id, 'adStatus': str(uuid4())}
    with patch.object(ad_feed_manager, 'dynamo') as dynamo_mock:
        with patch.object(ad_feed_manager, 'user_manager') as user_manager_mock:
            ad_feed_manager.on_ad_post_ad_status_change(post_id, new_item=new_item, old_item=old_item)
    assert user_manager_mock.mock_calls == [
        call.dynamo.generate_user_ids_by_ads_disabled(False, exclude_user_id=user_id)
    ]
    user_id_gen = user_manager_mock.dynamo.generate_user_ids_by_ads_disabled.return_value
    assert dynamo_mock.mock_calls == [call.add_ad_post_for_users(post_id, user_id_gen)]


def test_on_ad_post_ad_status_change_from_active(ad_feed_manager):
    user_id, post_id = str(uuid4()), str(uuid4())
    new_item = {'postId': post_id, 'postedByUserId': user_id, 'adStatus': str(uuid4())}
    old_item = {'postId': post_id, 'postedByUserId': user_id, 'adStatus': AdStatus.ACTIVE}
    with patch.object(ad_feed_manager, 'dynamo') as dynamo_mock:
        ad_feed_manager.on_ad_post_ad_status_change(post_id, new_item=new_item, old_item=old_item)
    assert dynamo_mock.mock_calls == [call.delete_by_post(post_id)]


def test_on_post_view_last_viewed_at_change_throws_if_not_changed(ad_feed_manager):
    post_id = str(uuid4())
    item = {'postId': post_id, 'lastViewedAt': str(uuid4())}
    with pytest.raises(AssertionError, match=' lastViewedAt '):
        ad_feed_manager.on_post_view_last_viewed_at_change(post_id, new_item=item, old_item=item)

    old_item = {'postId': post_id}
    new_item = {**old_item, 'lastViewedAt': None}
    with pytest.raises(AssertionError, match=' lastViewedAt '):
        ad_feed_manager.on_post_view_last_viewed_at_change(post_id, new_item=new_item, old_item=old_item)


@pytest.mark.parametrize('ad_status', [None, AdStatus.NOT_AD, AdStatus.PENDING, AdStatus.INACTIVE])
def test_on_post_view_last_viewed_at_change_does_nothing_for_non_active_ads(ad_feed_manager, ad_status):
    post_id, user_id, lva = str(uuid4()), str(uuid4()), str(uuid4())
    post_view_item = {'postId': post_id, 'sortKey': f'view/{user_id}', 'lastViewedAt': lva}
    post_item = {'postId': post_id, 'postType': 'pt', 'postedByUserId': 'pduid', 'adStatus': ad_status}
    post = ad_feed_manager.post_manager.init_post(post_item)
    with patch.object(ad_feed_manager.post_manager, 'get_post', return_value=post):
        with patch.object(ad_feed_manager, 'dynamo') as dynamo_mock:
            ad_feed_manager.on_post_view_last_viewed_at_change(post_id, new_item=post_view_item)
    assert dynamo_mock.mock_calls == []


def test_on_post_view_last_viewed_at_change_records_for_active_ads(ad_feed_manager):
    post_id, user_id, lva = str(uuid4()), str(uuid4()), str(uuid4())
    post_view_item = {'postId': post_id, 'sortKey': f'view/{user_id}', 'lastViewedAt': lva}
    post_item = {'postId': post_id, 'postType': 'pt', 'postedByUserId': 'pbuid', 'adStatus': AdStatus.ACTIVE}
    post = ad_feed_manager.post_manager.init_post(post_item)
    with patch.object(ad_feed_manager.post_manager, 'get_post', return_value=post):
        with patch.object(ad_feed_manager, 'dynamo') as dynamo_mock:
            ad_feed_manager.on_post_view_last_viewed_at_change(post_id, new_item=post_view_item)
    assert dynamo_mock.mock_calls == [call.set_last_viewed_at(post_id, user_id, lva)]


def test_on_user_ads_disabled_change_throws_if_not_changed(ad_feed_manager):
    user_id = str(uuid4())
    item = {'userId': user_id, 'adsDisabled': True}
    with pytest.raises(AssertionError, match=' adsDisabled '):
        ad_feed_manager.on_user_ads_disabled_change(user_id, new_item=item, old_item=item)

    old_item = {'userId': user_id}
    new_item = {**old_item, 'adsDisabled': False}
    with pytest.raises(AssertionError, match=' adsDisabled '):
        ad_feed_manager.on_user_ads_disabled_change(user_id, new_item=new_item, old_item=old_item)


@pytest.mark.parametrize('old_ads_disabled', [None, False])
def test_on_user_ads_disabled_change_to_true(ad_feed_manager, old_ads_disabled):
    user_id = str(uuid4())
    new_item = {'userId': user_id, 'adsDisabled': str(uuid4())}
    old_item = {'userId': user_id}
    if old_ads_disabled is not None:
        old_item['adsDisabled'] = old_ads_disabled
    with patch.object(ad_feed_manager, 'dynamo') as dynamo_mock:
        ad_feed_manager.on_user_ads_disabled_change(user_id, new_item=new_item, old_item=old_item)
    assert dynamo_mock.mock_calls == [call.delete_by_user(user_id)]


@pytest.mark.parametrize('new_ads_disabled', [None, False])
def test_on_user_ads_disabled_change_from_true(ad_feed_manager, new_ads_disabled):
    user_id = str(uuid4())
    old_item = {'userId': user_id, 'adsDisabled': str(uuid4())}
    new_item = {'userId': user_id}
    if new_ads_disabled is not None:
        new_item['adsDisabled'] = new_ads_disabled
    with patch.object(ad_feed_manager, 'dynamo') as dynamo_mock:
        with patch.object(ad_feed_manager, 'post_manager') as post_manager_mock:
            ad_feed_manager.on_user_ads_disabled_change(user_id, new_item=new_item, old_item=old_item)
    assert post_manager_mock.mock_calls == [
        call.dynamo.generate_post_ids_by_ad_status(AdStatus.ACTIVE, exclude_posted_by_user_id=user_id)
    ]
    post_id_gen = post_manager_mock.dynamo.generate_post_ids_by_ad_status.return_value
    assert dynamo_mock.mock_calls == [call.add_ad_posts_for_user(user_id, post_id_gen)]


def test_on_user_delete(ad_feed_manager):
    user_id = str(uuid4())
    with patch.object(ad_feed_manager, 'dynamo') as dynamo_mock:
        ad_feed_manager.on_user_delete(user_id, old_item={})
    assert dynamo_mock.mock_calls == [call.delete_by_user(user_id)]


def test_on_post_view_focus_last_viewed_at_change_throws_if_no_change(ad_feed_manager):
    post_id = str(uuid4())
    item = {'postId': post_id}
    with pytest.raises(AssertionError, match=' focusLastViewedAt '):
        ad_feed_manager.on_post_view_focus_last_viewed_at_change(post_id, new_item=item)
    item = {'postId': post_id, 'focusLastViewsAt': 'any-string'}
    with pytest.raises(AssertionError, match=' focusLastViewedAt '):
        ad_feed_manager.on_post_view_focus_last_viewed_at_change(post_id, new_item=item, old_item=item)


@pytest.mark.parametrize(
    'adStatus, owner, adPayment',
    [
        ['anything-but-ACTIVE', False, 1],
        [AdStatus.ACTIVE, True, 1],
        [AdStatus.ACTIVE, False, None],
        [AdStatus.ACTIVE, False, 0],
    ],
)
def test_on_post_view_focus_last_viewed_at_change_does_nothing_if_not_active_ad(
    ad_feed_manager, adStatus, owner, adPayment
):
    post_id, user_id = str(uuid4()), str(uuid4())
    old_item = {'partitionKey': f'post/{post_id}', 'sortKey': f'view/{user_id}'}
    new_item = {**old_item, 'focusLastViewedAt': pendulum.now('utc').to_iso8601_string()}
    post_item = {
        'postId': post_id,
        'postType': 'pt',
        'postedByUserId': user_id if owner else str(uuid4()),
        'adStatus': adStatus,
        'adPayment': adPayment,
    }
    post = ad_feed_manager.post_manager.init_post(post_item)
    with patch.object(ad_feed_manager.post_manager, 'get_post', return_value=post):
        with patch.object(ad_feed_manager, 'dynamo') as dynamo_mock:
            ad_feed_manager.on_post_view_focus_last_viewed_at_change(
                post_id, new_item=new_item, old_item=old_item
            )
    assert dynamo_mock.mock_calls == []
    assert ad_feed_manager.real_transactions_client.mock_calls == []


def test_on_post_view_focus_last_viewed_at_change_ad_payment_period_not_set(ad_feed_manager):
    post_id, user_id, post_owner_id = str(uuid4()), str(uuid4()), str(uuid4())
    amount = Decimal('0.1')
    focus_lva = pendulum.now('utc')
    old_item = {'partitionKey': f'post/{post_id}', 'sortKey': f'view/{user_id}'}
    new_item = {**old_item, 'focusLastViewedAt': focus_lva.to_iso8601_string()}
    post_item = {
        'postId': post_id,
        'postType': 'pt',
        'postedByUserId': post_owner_id,
        'adStatus': AdStatus.ACTIVE,
        'adPayment': amount,
    }
    post = ad_feed_manager.post_manager.init_post(post_item)
    with patch.object(ad_feed_manager.post_manager, 'get_post', return_value=post):
        with patch.object(ad_feed_manager, 'dynamo') as dynamo_mock:
            ad_feed_manager.on_post_view_focus_last_viewed_at_change(
                post_id, new_item=new_item, old_item=old_item
            )
    assert dynamo_mock.mock_calls == [
        call.get(post_id, user_id),
        call.get(post_id, user_id).__contains__('lastPaymentForViewAt'),
        call.record_payment_start(post_id, user_id, focus_lva, None),
        call.record_payment_finish(post_id, user_id),
    ]
    assert ad_feed_manager.real_transactions_client.mock_calls == [
        call.pay_for_ad_view(user_id, post_owner_id, post_id, amount)
    ]


def test_on_post_view_focus_last_viewed_at_change_ad_payment_period_is_set_first_view(ad_feed_manager):
    post_id, user_id, post_owner_id = str(uuid4()), str(uuid4()), str(uuid4())
    amount = Decimal('0.1')
    focus_lva = pendulum.now('utc')
    old_item = {'partitionKey': f'post/{post_id}', 'sortKey': f'view/{user_id}'}
    new_item = {**old_item, 'focusLastViewedAt': focus_lva.to_iso8601_string()}
    post_item = {
        'postId': post_id,
        'postType': 'pt',
        'postedByUserId': post_owner_id,
        'adStatus': AdStatus.ACTIVE,
        'adPayment': amount,
        'adPaymentPeriod': 'P1D',
    }
    post = ad_feed_manager.post_manager.init_post(post_item)
    ad_feed_manager.dynamo.add_ad_post_for_users(post_id, iter([user_id]))
    org_ad_feed_item = ad_feed_manager.dynamo.get(post_id, user_id)
    with patch.object(ad_feed_manager.post_manager, 'get_post', return_value=post):
        ad_feed_manager.on_post_view_focus_last_viewed_at_change(post_id, new_item=new_item, old_item=old_item)
    assert ad_feed_manager.real_transactions_client.mock_calls == [
        call.pay_for_ad_view(user_id, post_owner_id, post_id, amount)
    ]
    new_ad_feed_item = ad_feed_manager.dynamo.get(post_id, user_id)
    last_payment_finished_at = pendulum.parse(new_ad_feed_item['lastPaymentFinishedAt'])
    assert focus_lva <= last_payment_finished_at <= pendulum.now('utc')
    assert new_ad_feed_item == {
        **org_ad_feed_item,
        'paymentCount': 1,
        'lastPaymentForViewAt': focus_lva.to_iso8601_string(),
        'lastPaymentFinishedAt': last_payment_finished_at.to_iso8601_string(),
    }


def test_on_post_view_focus_last_viewed_at_change_ad_payment_period_is_set_second_view_too_soon(ad_feed_manager):
    post_id, user_id, post_owner_id = str(uuid4()), str(uuid4()), str(uuid4())
    amount = Decimal('0.1')
    focus_lva = pendulum.now('utc')
    old_item = {'partitionKey': f'post/{post_id}', 'sortKey': f'view/{user_id}'}
    new_item = {**old_item, 'focusLastViewedAt': focus_lva.to_iso8601_string()}
    post_item = {
        'postId': post_id,
        'postType': 'pt',
        'postedByUserId': post_owner_id,
        'adStatus': AdStatus.ACTIVE,
        'adPayment': amount,
        'adPaymentPeriod': 'P1D',
    }
    post = ad_feed_manager.post_manager.init_post(post_item)
    ad_feed_manager.dynamo.add_ad_post_for_users(post_id, iter([user_id]))
    prev_lva = focus_lva.subtract(days=1).add(microseconds=1)
    ad_feed_manager.dynamo.record_payment_start(post_id, user_id, prev_lva, None)
    org_ad_feed_item = ad_feed_manager.dynamo.get(post_id, user_id)
    with patch.object(ad_feed_manager.post_manager, 'get_post', return_value=post):
        ad_feed_manager.on_post_view_focus_last_viewed_at_change(post_id, new_item=new_item, old_item=old_item)
    assert ad_feed_manager.real_transactions_client.mock_calls == []
    assert ad_feed_manager.dynamo.get(post_id, user_id) == org_ad_feed_item


def test_on_post_view_focus_last_viewed_at_change_ad_payment_period_is_set_second_view_after(ad_feed_manager):
    post_id, user_id, post_owner_id = str(uuid4()), str(uuid4()), str(uuid4())
    amount = Decimal('0.1')
    focus_lva = pendulum.now('utc')
    old_item = {'partitionKey': f'post/{post_id}', 'sortKey': f'view/{user_id}'}
    new_item = {**old_item, 'focusLastViewedAt': focus_lva.to_iso8601_string()}
    post_item = {
        'postId': post_id,
        'postType': 'pt',
        'postedByUserId': post_owner_id,
        'adStatus': AdStatus.ACTIVE,
        'adPayment': amount,
        'adPaymentPeriod': 'P1D',
    }
    post = ad_feed_manager.post_manager.init_post(post_item)
    ad_feed_manager.dynamo.add_ad_post_for_users(post_id, iter([user_id]))
    prev_lva = focus_lva.subtract(days=1).subtract(microseconds=1)
    ad_feed_manager.dynamo.record_payment_start(post_id, user_id, prev_lva, None)
    ad_feed_manager.dynamo.record_payment_finish(post_id, user_id)
    org_ad_feed_item = ad_feed_manager.dynamo.get(post_id, user_id)
    with patch.object(ad_feed_manager.post_manager, 'get_post', return_value=post):
        ad_feed_manager.on_post_view_focus_last_viewed_at_change(post_id, new_item=new_item, old_item=old_item)
    assert ad_feed_manager.real_transactions_client.mock_calls == [
        call.pay_for_ad_view(user_id, post_owner_id, post_id, amount)
    ]
    new_ad_feed_item = ad_feed_manager.dynamo.get(post_id, user_id)
    last_payment_finished_at = pendulum.parse(new_ad_feed_item['lastPaymentFinishedAt'])
    assert focus_lva <= last_payment_finished_at <= pendulum.now('utc')
    assert new_ad_feed_item == {
        **org_ad_feed_item,
        'paymentCount': 2,
        'lastPaymentForViewAt': focus_lva.to_iso8601_string(),
        'lastPaymentFinishedAt': last_payment_finished_at.to_iso8601_string(),
    }
