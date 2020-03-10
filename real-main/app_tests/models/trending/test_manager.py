import math

import pendulum
import pytest

from app.models.trending.enums import TrendingItemType


def test_record_view_count_new_trending(trending_manager):
    item_type = trending_manager.enums.TrendingItemType.USER
    item_id = 'user-id'
    view_count = 4

    trending_item = trending_manager.record_view_count(item_type, item_id, view_count)
    assert trending_item['pendingViewCount'] == 0
    assert trending_item['gsiK3SortKey'] == view_count


def test_record_view_count_existing_trending(trending_manager):
    item_type = trending_manager.enums.TrendingItemType.POST
    item_id = 'user-id'
    org_view_count = 4
    update_view_count = 5

    # create a trending item
    org_trending_item = trending_manager.record_view_count(item_type, item_id, org_view_count)
    assert org_trending_item['pendingViewCount'] == 0

    # update the trending item
    updated_trending_item = trending_manager.record_view_count(item_type, item_id, update_view_count)
    assert updated_trending_item['pendingViewCount'] == update_view_count
    assert updated_trending_item['gsiK3SortKey'] == org_trending_item['gsiK3SortKey']
    assert updated_trending_item['gsiA1SortKey'] == org_trending_item['gsiA1SortKey']


def test_record_view_count_multiple_records_with_same_timestamp(trending_manager):
    item_type = trending_manager.enums.TrendingItemType.POST
    item_id = 'user-id'
    org_view_count = 4
    update_view_count = 5
    now = pendulum.now('utc')

    # create a trending item
    item = trending_manager.record_view_count(item_type, item_id, org_view_count, now=now)
    assert item['pendingViewCount'] == 0

    # update the trending item
    item = trending_manager.record_view_count(item_type, item_id, update_view_count, now=now)
    assert item['pendingViewCount'] == 0
    assert item['gsiK3SortKey'] == org_view_count + update_view_count


def test_calculate_new_score_decay(trending_manager):
    now = pendulum.now('utc')
    old_score = 10

    # one full day
    last_indexed_at = now - pendulum.duration(days=1)
    new_score = trending_manager.calculate_new_score(old_score, last_indexed_at, 0, now)
    assert float(new_score) == pytest.approx(10 / math.e)

    # half life
    last_indexed_at = now - math.log(2) * pendulum.duration(days=1)
    new_score = trending_manager.calculate_new_score(old_score, last_indexed_at, 0, now)
    assert float(new_score) == pytest.approx(5)

    # a minute
    last_indexed_at = now - pendulum.duration(minutes=1)
    new_score = trending_manager.calculate_new_score(old_score, last_indexed_at, 0, now)
    assert float(new_score) == pytest.approx(10 / math.exp(1.0 / 24 / 60))


def test_calculate_new_score_pending_views(trending_manager):
    now = pendulum.now('utc')
    old_score = 10
    pending_views = 10

    # one full day
    last_indexed_at = now - pendulum.duration(days=1)
    new_score = trending_manager.calculate_new_score(old_score, last_indexed_at, pending_views, now)
    assert float(new_score) == pytest.approx(10 / math.e + pending_views)

    # half life
    last_indexed_at = now - math.log(2) * pendulum.duration(days=1)
    new_score = trending_manager.calculate_new_score(old_score, last_indexed_at, pending_views, now)
    assert float(new_score) == pytest.approx(15)


def test_reindex_all_operates_on_correct_items(trending_manager):
    now = pendulum.now('utc')

    # add one user item now
    user_id = 'user-id'
    trending_manager.record_view_count(TrendingItemType.USER, user_id, 42, now=now)

    # add one post item in the future a second
    post_id_1 = 'post-id-1'
    trending_manager.record_view_count(TrendingItemType.POST, post_id_1, 9, now=(now + pendulum.duration(seconds=1)))

    # add one post item a day ago, give it some pending views
    post_id_2 = 'post-id-2'
    post_at_2 = now - pendulum.duration(days=1)
    trending_manager.record_view_count(TrendingItemType.POST, post_id_2, 10, now=post_at_2)
    trending_manager.record_view_count(TrendingItemType.POST, post_id_2, 5)

    # pull originals from db, save them
    org_user_items = list(trending_manager.dynamo.generate_trendings(TrendingItemType.USER))
    assert len(org_user_items) == 1
    assert org_user_items[0]['partitionKey'] == f'trending/{user_id}'

    org_post_items = list(trending_manager.dynamo.generate_trendings(TrendingItemType.POST))
    assert len(org_post_items) == 2
    assert org_post_items[0]['partitionKey'] == f'trending/{post_id_2}'
    assert org_post_items[1]['partitionKey'] == f'trending/{post_id_1}'

    # reindex just one of the post items
    trending_manager.reindex(TrendingItemType.POST, cutoff=now)

    # check the user item unchanged
    new_user_items = list(trending_manager.dynamo.generate_trendings(TrendingItemType.USER))
    assert new_user_items == org_user_items

    # check just one of the post items changed, and its new values are what we would expect
    new_post_items = list(trending_manager.dynamo.generate_trendings(TrendingItemType.POST))
    assert len(new_post_items) == 2
    assert new_post_items[1] == org_post_items[1]
    assert new_post_items[0]['partitionKey'] == f'trending/{post_id_2}'
    assert new_post_items[0]['pendingViewCount'] == 0
    assert new_post_items[0]['gsiA1SortKey'] == now.to_iso8601_string()
    assert float(new_post_items[0]['gsiK3SortKey']) == pytest.approx(10 / math.e + 5)

    # reindex again at the same values
    trending_manager.reindex(TrendingItemType.POST, cutoff=now)

    # check nothing changed
    assert list(trending_manager.dynamo.generate_trendings(TrendingItemType.USER)) == new_user_items
    assert list(trending_manager.dynamo.generate_trendings(TrendingItemType.POST)) == new_post_items


def test_reindex_deletes_as_needed(trending_manager):
    now = pendulum.now('utc')

    # add one post item just over a day ago
    post_id_1 = 'post-id-over'
    trending_manager.record_view_count(TrendingItemType.POST, post_id_1, 1, now=(now - pendulum.duration(hours=25)))

    # add another post item just under a day ago
    post_id_2 = 'post-id-under'
    trending_manager.record_view_count(TrendingItemType.POST, post_id_2, 1, now=(now - pendulum.duration(hours=23)))

    # check we can see those post items
    post_items = list(trending_manager.dynamo.generate_trendings(TrendingItemType.POST))
    assert len(post_items) == 2
    assert post_items[0]['partitionKey'] == f'trending/{post_id_1}'
    assert post_items[1]['partitionKey'] == f'trending/{post_id_2}'

    # reindex
    trending_manager.reindex(TrendingItemType.POST, cutoff=now)

    # check that one post item has disappeared, and the other has not
    post_items = list(trending_manager.dynamo.generate_trendings(TrendingItemType.POST))
    assert len(post_items) == 1
    assert post_items[0]['partitionKey'] == f'trending/{post_id_2}'
