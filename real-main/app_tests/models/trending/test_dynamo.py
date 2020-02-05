import pendulum
import pytest

from app.models.trending import enums, exceptions
from app.models.trending.dynamo import TrendingDynamo


@pytest.fixture
def trending_dynamo(dynamo_client):
    yield TrendingDynamo(dynamo_client)


def test_get_trending(trending_dynamo):
    # doesn't exist
    resp = trending_dynamo.get_trending('doesnt-exist')
    assert resp is None

    # create one, then make sure we can get it
    item_id = 'item-id'
    item_type = enums.TrendingItemType.USER
    trending_dynamo.create_trending(item_type, item_id, 42)
    resp = trending_dynamo.get_trending(item_id)
    assert resp['partitionKey'] == f'trending/{item_id}'


def test_delete_trending(trending_dynamo):
    item_id = 'item-id'
    item_type = enums.TrendingItemType.USER

    # doesn't exist
    resp = trending_dynamo.delete_trending(item_id)
    assert resp is None

    # create one, then make sure we can delete it
    trending_dynamo.create_trending(item_type, item_id, 42)
    resp = trending_dynamo.delete_trending(item_id)
    assert resp['partitionKey'] == f'trending/{item_id}'

    # make sure it's really gone
    resp = trending_dynamo.get_trending(item_id)
    assert resp is None


def test_create_trending(trending_dynamo):
    item_type = enums.TrendingItemType.POST
    item_id = 'item-id'
    view_count = 54
    now = pendulum.now('utc')

    # create one, check it's form
    resp = trending_dynamo.create_trending(item_type, item_id, view_count, now=now)
    assert resp == {
        'partitionKey': f'trending/{item_id}',
        'sortKey': '-',
        'gsiA1PartitionKey': f'trending/{item_type}',
        'gsiA1SortKey': now.to_iso8601_string(),
        'gsiK3PartitionKey': f'trending/{item_type}',
        'gsiK3SortKey': view_count,
        'schemaVersion': 0,
        'pendingViewCount': 0,
    }

    # check we can't create another for the same item
    with pytest.raises(exceptions.TrendingAlreadyExists):
        trending_dynamo.create_trending(item_type, item_id, view_count, now=now)


def test_increment_trending_pending_view_count(trending_dynamo):
    # doesn't exist
    with pytest.raises(exceptions.TrendingException):
        trending_dynamo.increment_trending_pending_view_count('doesnt-exist', 42)

    # create a trending
    item_type = enums.TrendingItemType.POST
    item_id = 'item-id'
    view_count = 54
    resp = trending_dynamo.create_trending(item_type, item_id, view_count)
    assert resp['pendingViewCount'] == 0

    # update its pending view count
    view_count_increment = 12
    resp = trending_dynamo.increment_trending_pending_view_count(item_id, view_count_increment)
    assert resp['pendingViewCount'] == view_count_increment

    # update its pending view count
    resp = trending_dynamo.increment_trending_pending_view_count(item_id, view_count_increment)
    assert resp['pendingViewCount'] == view_count_increment * 2


def test_cant_increment_trending_pending_view_count_at_or_before_last_indexed_at(trending_dynamo):
    # create a trending
    now = pendulum.now('utc')
    item_type = enums.TrendingItemType.POST
    item_id = 'item-id'
    view_count = 54
    resp = trending_dynamo.create_trending(item_type, item_id, view_count, now=now)
    assert resp['pendingViewCount'] == 0

    # can't update pendingViewCount at the same timestamp as was created at
    # should update viewCount directly
    with pytest.raises(exceptions.TrendingException):
        trending_dynamo.increment_trending_pending_view_count(item_id, 10, now=now)

    before = now - pendulum.duration(minutes=1)
    with pytest.raises(exceptions.TrendingException):
        trending_dynamo.increment_trending_pending_view_count(item_id, 10, now=before)


def test_increment_trending_view_count(trending_dynamo):
    # create a trending
    now = pendulum.now('utc')
    item_type = enums.TrendingItemType.POST
    item_id = 'item-id'
    view_count = 54
    resp = trending_dynamo.create_trending(item_type, item_id, view_count, now=now)
    assert resp['pendingViewCount'] == 0

    # can't update it with a timestamp in the future
    future = pendulum.now('utc')
    with pytest.raises(exceptions.TrendingException):
        trending_dynamo.increment_trending_view_count(item_id, 10, now=future)

    # can update it with a timestamp at the lastIndexedAt time
    resp = trending_dynamo.increment_trending_view_count(item_id, 10, now=now)
    assert resp['gsiK3SortKey'] == 64


def test_update_trending_score_success(trending_dynamo):
    # create a trending
    item_type = enums.TrendingItemType.USER
    item_id = 'item-id'
    view_count = 54
    resp = trending_dynamo.create_trending(item_type, item_id, view_count)
    assert resp['partitionKey'] == f'trending/{item_id}'

    # give it some pending views
    view_count_increment = 12
    resp = trending_dynamo.increment_trending_pending_view_count(item_id, view_count_increment)
    assert resp['pendingViewCount'] == view_count_increment
    old_last_indexed_at = pendulum.parse(resp['gsiA1SortKey']).in_tz('utc')

    # now update its score
    new_score = 13
    new_last_indexed_at = pendulum.now('utc')
    view_count_change_abs = 12
    resp = trending_dynamo.update_trending_score(
        item_id, new_score, new_last_indexed_at, old_last_indexed_at, view_count_change_abs,
    )
    assert resp['gsiK3SortKey'] == new_score
    assert resp['gsiA1SortKey'] == new_last_indexed_at.to_iso8601_string()
    assert resp['pendingViewCount'] == view_count_increment - view_count_change_abs


def test_update_trending_score_error_conditions(trending_dynamo):
    # doesn't exist
    with pytest.raises(Exception):
        trending_dynamo.update_trending_score('doesnt-exist', 42, pendulum.now('utc'), pendulum.now('utc'), 24)

    # create a trending
    item_type = enums.TrendingItemType.USER
    item_id = 'item-id'
    view_count = 1
    now = pendulum.now('utc')
    resp = trending_dynamo.create_trending(item_type, item_id, view_count, now=now)
    assert resp['partitionKey'] == f'trending/{item_id}'

    # change in pending view count to big
    with pytest.raises(Exception):
        trending_dynamo.update_trending_score(item_id, 42, pendulum.now('utc'), now, 1)

    # score last updated at is wrong
    with pytest.raises(Exception):
        trending_dynamo.update_trending_score(item_id, 42, pendulum.now('utc'), pendulum.now('utc'), 0)


def test_generate_trendings_basic(trending_dynamo):
    # test an empty response
    resp = list(trending_dynamo.generate_trendings(enums.TrendingItemType.USER))
    assert len(resp) == 0

    # create a post trending
    item_type = enums.TrendingItemType.POST
    item_id = 'post-item-id'
    view_count = 5
    now = pendulum.now('utc')
    resp = trending_dynamo.create_trending(item_type, item_id, view_count, now=now)
    assert resp['partitionKey'] == f'trending/{item_id}'

    # generate the post trendings, make sure all fields we need are included
    resp = list(trending_dynamo.generate_trendings(item_type))
    assert len(resp) == 1
    assert resp[0]['partitionKey'] == f'trending/{item_id}'
    assert resp[0]['pendingViewCount'] == 0
    assert resp[0]['gsiA1PartitionKey'] == f'trending/{item_type}'
    assert resp[0]['gsiA1SortKey'] == now.to_iso8601_string()
    assert resp[0]['gsiK3PartitionKey'] == f'trending/{item_type}'
    assert resp[0]['gsiK3SortKey'] == view_count


def test_generate_trendings_different_types(trending_dynamo):
    # create a post trending
    post_item_type = enums.TrendingItemType.POST
    post_item_id = 'post-item-id'
    resp = trending_dynamo.create_trending(post_item_type, post_item_id, 0)
    assert resp['partitionKey'] == f'trending/{post_item_id}'

    # create a user trending
    user_item_type = enums.TrendingItemType.USER
    user_item_id = 'user-item-id'
    resp = trending_dynamo.create_trending(user_item_type, user_item_id, 0)
    assert resp['partitionKey'] == f'trending/{user_item_id}'

    # generate just the post trendings
    resp = list(trending_dynamo.generate_trendings(enums.TrendingItemType.POST))
    assert len(resp) == 1
    assert resp[0]['partitionKey'] == f'trending/{post_item_id}'

    # generate just the user trendings
    resp = list(trending_dynamo.generate_trendings(enums.TrendingItemType.USER))
    assert len(resp) == 1
    assert resp[0]['partitionKey'] == f'trending/{user_item_id}'


def test_generate_trendings_max_last_indexed_at_cutoff_and_order(trending_dynamo):
    # create a two post trendings
    item_type = enums.TrendingItemType.POST
    item_id_1 = 'item-id-1'
    item_id_2 = 'item-id-2'
    now = pendulum.now('utc')
    now_1 = now - pendulum.duration(hours=1)
    now_2 = now + pendulum.duration(hours=1)

    resp = trending_dynamo.create_trending(item_type, item_id_1, 0, now=now_1)
    assert resp['partitionKey'] == f'trending/{item_id_1}'

    resp = trending_dynamo.create_trending(item_type, item_id_2, 0, now=now_2)
    assert resp['partitionKey'] == f'trending/{item_id_2}'

    # generate no trendings
    resp = list(trending_dynamo.generate_trendings(item_type, max_last_indexed_at=(now - pendulum.duration(hours=2))))
    assert len(resp) == 0

    # generate the first trendings
    resp = list(trending_dynamo.generate_trendings(item_type, max_last_indexed_at=now))
    assert len(resp) == 1
    assert resp[0]['partitionKey'] == f'trending/{item_id_1}'

    # generate all the trendings
    resp = list(trending_dynamo.generate_trendings(item_type, max_last_indexed_at=(now + pendulum.duration(hours=2))))
    assert len(resp) == 2
    assert resp[0]['partitionKey'] == f'trending/{item_id_1}'
    assert resp[1]['partitionKey'] == f'trending/{item_id_2}'
