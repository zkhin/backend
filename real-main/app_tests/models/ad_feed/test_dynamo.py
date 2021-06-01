from uuid import uuid4

import pendulum
import pytest

from app.models.ad_feed.dynamo import AdFeedDynamo


@pytest.fixture
def ad_feed_dynamo(dynamo_ad_feed_client):
    yield AdFeedDynamo(dynamo_ad_feed_client)


def test_add_ad_post_for_users(ad_feed_dynamo):
    pid1, pid2 = str(uuid4()), str(uuid4())
    uid1, uid2, uid3 = str(uuid4()), str(uuid4()), str(uuid4())
    assert ad_feed_dynamo.client.table.scan()['Items'] == []

    # add nothing, verify
    user_id_generator = iter([])
    ad_feed_dynamo.add_ad_post_for_users(pid1, user_id_generator)
    assert ad_feed_dynamo.client.table.scan()['Items'] == []

    # add one, verify
    user_id_generator = iter([uid1])
    ad_feed_dynamo.add_ad_post_for_users(pid1, user_id_generator)
    assert ad_feed_dynamo.client.table.scan()['Items'] == [
        {'postId': pid1, 'userId': uid1, 'lastViewedAt': '!'},
    ]

    # add two, verify
    user_id_generator = iter([uid2, uid3])
    ad_feed_dynamo.add_ad_post_for_users(pid2, user_id_generator)
    items = ad_feed_dynamo.client.table.scan()['Items']
    assert len(items) == 3
    assert {'postId': pid1, 'userId': uid1, 'lastViewedAt': '!'} in items
    assert {'postId': pid2, 'userId': uid2, 'lastViewedAt': '!'} in items
    assert {'postId': pid2, 'userId': uid3, 'lastViewedAt': '!'} in items


def test_add_ad_posts_for_user(ad_feed_dynamo):
    pid1, pid2, pid3 = str(uuid4()), str(uuid4()), str(uuid4())
    uid1, uid2 = str(uuid4()), str(uuid4())
    assert ad_feed_dynamo.client.table.scan()['Items'] == []

    # add nothing, verify
    post_id_generator = iter([])
    ad_feed_dynamo.add_ad_posts_for_user(uid1, post_id_generator)
    assert ad_feed_dynamo.client.table.scan()['Items'] == []

    # add one, verify
    post_id_generator = iter([pid1])
    ad_feed_dynamo.add_ad_posts_for_user(uid1, post_id_generator)
    assert ad_feed_dynamo.client.table.scan()['Items'] == [
        {'postId': pid1, 'userId': uid1, 'lastViewedAt': '!'},
    ]

    # add two, verify
    post_id_generator = iter([pid2, pid3])
    ad_feed_dynamo.add_ad_posts_for_user(uid2, post_id_generator)
    items = ad_feed_dynamo.client.table.scan()['Items']
    assert len(items) == 3
    assert {'postId': pid1, 'userId': uid1, 'lastViewedAt': '!'} in items
    assert {'postId': pid2, 'userId': uid2, 'lastViewedAt': '!'} in items
    assert {'postId': pid3, 'userId': uid2, 'lastViewedAt': '!'} in items


def test_set_last_viewed_at(ad_feed_dynamo):
    uid1, uid2 = str(uuid4()), str(uuid4())
    pid1, pid2 = str(uuid4()), str(uuid4())
    lva = pendulum.now('utc')

    # verify can't set for an item that doesn't exist
    with pytest.raises(ad_feed_dynamo.client.exceptions.ConditionalCheckFailedException):
        ad_feed_dynamo.set_last_viewed_at(pid1, uid1, lva.to_iso8601_string())

    # add an item, verify
    ad_feed_dynamo.add_ad_posts_for_user(uid1, iter([pid1]))
    assert ad_feed_dynamo.client.table.scan()['Items'] == [
        {'postId': pid1, 'userId': uid1, 'lastViewedAt': '!'},
    ]

    # udpate the lastviewedat on that item, veirfy
    ad_feed_dynamo.set_last_viewed_at(pid1, uid1, 'an-iso-str')
    assert ad_feed_dynamo.client.table.scan()['Items'] == [
        {'postId': pid1, 'userId': uid1, 'lastViewedAt': 'an-iso-str'},
    ]

    # add two more items, verify
    ad_feed_dynamo.add_ad_posts_for_user(uid1, iter([pid2]))
    ad_feed_dynamo.add_ad_posts_for_user(uid2, iter([pid1]))
    items = ad_feed_dynamo.client.table.scan()['Items']
    assert len(items) == 3
    assert {'postId': pid1, 'userId': uid1, 'lastViewedAt': 'an-iso-str'} in items
    assert {'postId': pid2, 'userId': uid1, 'lastViewedAt': '!'} in items
    assert {'postId': pid1, 'userId': uid2, 'lastViewedAt': '!'} in items

    # udpate the lastviewedat on the first item again, veirfy
    ad_feed_dynamo.set_last_viewed_at(pid1, uid1, 'diff-iso-str')
    items = ad_feed_dynamo.client.table.scan()['Items']
    assert len(items) == 3
    assert {'postId': pid1, 'userId': uid1, 'lastViewedAt': 'diff-iso-str'} in items
    assert {'postId': pid2, 'userId': uid1, 'lastViewedAt': '!'} in items
    assert {'postId': pid1, 'userId': uid2, 'lastViewedAt': '!'} in items


def test_record_payment_start(ad_feed_dynamo):
    pid, uid = str(uuid4()), str(uuid4())
    lpfva = pendulum.now('utc')

    # verify can't operate on ad_feed item that DNE
    with pytest.raises(ad_feed_dynamo.client.exceptions.ConditionalCheckFailedException):
        ad_feed_dynamo.record_payment_start(pid, uid, lpfva, None)

    # verify we get an error is we pass a mismatching oldLastPaymentForViewAt
    ad_feed_dynamo.add_ad_post_for_users(pid, iter([uid]))
    org_item = ad_feed_dynamo.get(pid, uid)
    with pytest.raises(ad_feed_dynamo.client.exceptions.ConditionalCheckFailedException):
        ad_feed_dynamo.record_payment_start(pid, uid, lpfva, lpfva.subtract(minutes=5))
    assert ad_feed_dynamo.get(pid, uid) == org_item

    # verify we can record payment start
    new_item = {**org_item, 'lastPaymentForViewAt': lpfva.to_iso8601_string()}
    assert ad_feed_dynamo.record_payment_start(pid, uid, lpfva, None) == new_item
    assert ad_feed_dynamo.get(pid, uid) == new_item

    # verify we get an error is we pass a mismatching oldLastPaymentForViewAt
    lpfva2 = pendulum.now('utc')
    with pytest.raises(ad_feed_dynamo.client.exceptions.ConditionalCheckFailedException):
        ad_feed_dynamo.record_payment_start(pid, uid, lpfva2, lpfva2.subtract(hours=1))
    assert ad_feed_dynamo.get(pid, uid) == new_item

    # verify we can record payment start again
    new_item = {**new_item, 'lastPaymentForViewAt': lpfva2.to_iso8601_string()}
    assert ad_feed_dynamo.record_payment_start(pid, uid, lpfva2, lpfva) == new_item
    assert ad_feed_dynamo.get(pid, uid) == new_item


def test_record_payment_finish(ad_feed_dynamo):
    pid, uid = str(uuid4()), str(uuid4())

    # verify can't operate on ad_feed item that DNE
    with pytest.raises(ad_feed_dynamo.client.exceptions.ConditionalCheckFailedException):
        ad_feed_dynamo.record_payment_finish(pid, uid)

    # verify we can record payment finish
    ad_feed_dynamo.add_ad_post_for_users(pid, iter([uid]))
    org_item = ad_feed_dynamo.get(pid, uid)
    now = pendulum.now('utc')
    new_item = {**org_item, 'paymentCount': 1, 'lastPaymentFinishedAt': now.to_iso8601_string()}
    assert ad_feed_dynamo.record_payment_finish(pid, uid, now=now) == new_item
    assert ad_feed_dynamo.get(pid, uid) == new_item

    # verify we can record payment finish again
    now = pendulum.now('utc')
    new_item = {**new_item, 'paymentCount': 2, 'lastPaymentFinishedAt': now.to_iso8601_string()}
    assert ad_feed_dynamo.record_payment_finish(pid, uid, now=now) == new_item
    assert ad_feed_dynamo.get(pid, uid) == new_item


def test_delete_by_post(ad_feed_dynamo):
    # add some starting data, verify
    uid1, uid2 = str(uuid4()), str(uuid4())
    pid1, pid2, pid3 = str(uuid4()), str(uuid4()), str(uuid4())
    ad_feed_dynamo.add_ad_post_for_users(pid1, iter([uid1, uid2]))
    ad_feed_dynamo.add_ad_post_for_users(pid2, iter([uid1]))
    items = ad_feed_dynamo.client.table.scan()['Items']
    assert len(items) == 3
    assert {'postId': pid1, 'userId': uid1, 'lastViewedAt': '!'} in items
    assert {'postId': pid1, 'userId': uid2, 'lastViewedAt': '!'} in items
    assert {'postId': pid2, 'userId': uid1, 'lastViewedAt': '!'} in items

    # test delete none, verify
    ad_feed_dynamo.delete_by_post(pid3)
    items = ad_feed_dynamo.client.table.scan()['Items']
    assert len(items) == 3
    assert {'postId': pid1, 'userId': uid1, 'lastViewedAt': '!'} in items
    assert {'postId': pid1, 'userId': uid2, 'lastViewedAt': '!'} in items
    assert {'postId': pid2, 'userId': uid1, 'lastViewedAt': '!'} in items

    # test delete one, verify
    ad_feed_dynamo.delete_by_post(pid2)
    items = ad_feed_dynamo.client.table.scan()['Items']
    assert len(items) == 2
    assert {'postId': pid1, 'userId': uid1, 'lastViewedAt': '!'} in items
    assert {'postId': pid1, 'userId': uid2, 'lastViewedAt': '!'} in items

    # test delete two, verify
    ad_feed_dynamo.delete_by_post(pid1)
    assert ad_feed_dynamo.client.table.scan()['Items'] == []


def test_delete_by_user(ad_feed_dynamo):
    # add some starting data, verify
    uid1, uid2, uid3 = str(uuid4()), str(uuid4()), str(uuid4())
    pid1, pid2 = str(uuid4()), str(uuid4())
    ad_feed_dynamo.add_ad_posts_for_user(uid1, iter([pid1, pid2]))
    ad_feed_dynamo.add_ad_posts_for_user(uid2, iter([pid1]))
    items = ad_feed_dynamo.client.table.scan()['Items']
    assert len(items) == 3
    assert {'postId': pid1, 'userId': uid1, 'lastViewedAt': '!'} in items
    assert {'postId': pid1, 'userId': uid2, 'lastViewedAt': '!'} in items
    assert {'postId': pid2, 'userId': uid1, 'lastViewedAt': '!'} in items

    # test delete none, verify
    ad_feed_dynamo.delete_by_user(uid3)
    items = ad_feed_dynamo.client.table.scan()['Items']
    assert len(items) == 3
    assert {'postId': pid1, 'userId': uid1, 'lastViewedAt': '!'} in items
    assert {'postId': pid1, 'userId': uid2, 'lastViewedAt': '!'} in items
    assert {'postId': pid2, 'userId': uid1, 'lastViewedAt': '!'} in items

    # test delete one, verify
    ad_feed_dynamo.delete_by_user(uid2)
    items = ad_feed_dynamo.client.table.scan()['Items']
    assert len(items) == 2
    assert {'postId': pid1, 'userId': uid1, 'lastViewedAt': '!'} in items
    assert {'postId': pid2, 'userId': uid1, 'lastViewedAt': '!'} in items

    # test delete two, verify
    ad_feed_dynamo.delete_by_user(uid1)
    assert ad_feed_dynamo.client.table.scan()['Items'] == []


def test_generate_keys_by_post(ad_feed_dynamo):
    # add some starting data, verify
    uid1, uid2 = str(uuid4()), str(uuid4())
    pid1, pid2, pid3 = str(uuid4()), str(uuid4()), str(uuid4())
    ad_feed_dynamo.add_ad_post_for_users(pid1, iter([uid1, uid2]))
    ad_feed_dynamo.add_ad_post_for_users(pid2, iter([uid1]))
    items = ad_feed_dynamo.client.table.scan()['Items']
    assert len(items) == 3
    assert {'postId': pid1, 'userId': uid1, 'lastViewedAt': '!'} in items
    assert {'postId': pid1, 'userId': uid2, 'lastViewedAt': '!'} in items
    assert {'postId': pid2, 'userId': uid1, 'lastViewedAt': '!'} in items

    # verify generate none, one, and two
    assert list(ad_feed_dynamo.generate_keys_by_post(pid3)) == []
    assert list(ad_feed_dynamo.generate_keys_by_post(pid2)) == [
        {'postId': pid2, 'userId': uid1},
    ]
    items = list(ad_feed_dynamo.generate_keys_by_post(pid1))
    assert len(items) == 2
    assert {'postId': pid1, 'userId': uid1} in items
    assert {'postId': pid1, 'userId': uid2} in items


def test_generate_keys_by_user(ad_feed_dynamo):
    # add some starting data, verify
    uid1, uid2, uid3 = str(uuid4()), str(uuid4()), str(uuid4())
    pid1, pid2 = str(uuid4()), str(uuid4())
    ad_feed_dynamo.add_ad_posts_for_user(uid1, iter([pid1, pid2]))
    ad_feed_dynamo.add_ad_posts_for_user(uid2, iter([pid1]))
    items = ad_feed_dynamo.client.table.scan()['Items']
    assert len(items) == 3
    assert {'postId': pid1, 'userId': uid1, 'lastViewedAt': '!'} in items
    assert {'postId': pid1, 'userId': uid2, 'lastViewedAt': '!'} in items
    assert {'postId': pid2, 'userId': uid1, 'lastViewedAt': '!'} in items

    # verify generate none, one, and two
    assert list(ad_feed_dynamo.generate_keys_by_user(uid3)) == []
    assert list(ad_feed_dynamo.generate_keys_by_user(uid2)) == [
        {'postId': pid1, 'userId': uid2},
    ]
    items = list(ad_feed_dynamo.generate_keys_by_user(uid1))
    assert len(items) == 2
    assert {'postId': pid1, 'userId': uid1} in items
    assert {'postId': pid2, 'userId': uid1} in items
