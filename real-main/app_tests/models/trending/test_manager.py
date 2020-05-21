import math
import uuid

import pendulum
import pytest

from app.models.post.enums import PostType
from app.models.trending.enums import TrendingItemType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id = str(uuid.uuid4())
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username=user_id)
    yield user_manager.create_cognito_only_user(user_id, str(uuid.uuid4())[:8])


@pytest.fixture
def real_user(user_manager, cognito_client):
    user_id = str(uuid.uuid4())
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username=user_id)
    yield user_manager.create_cognito_only_user(user_id, 'real')


def test_increment_score_new_trending(trending_manager):
    item_type = trending_manager.enums.TrendingItemType.USER
    item_id = 'user-id'
    amount = 4

    trending_item = trending_manager.increment_score(item_type, item_id, amount=amount)
    assert trending_item['pendingViewCount'] == 0
    assert trending_item['gsiK3SortKey'] == amount


def test_increment_score_existing_trending(trending_manager):
    item_type = trending_manager.enums.TrendingItemType.POST
    item_id = 'user-id'
    org_amount = 4
    update_amount = 5

    # create a trending item
    org_trending_item = trending_manager.increment_score(item_type, item_id, amount=org_amount)
    assert org_trending_item['pendingViewCount'] == 0

    # update the trending item
    updated_trending_item = trending_manager.increment_score(item_type, item_id, amount=update_amount)
    assert updated_trending_item['pendingViewCount'] == update_amount
    assert updated_trending_item['gsiK3SortKey'] == org_trending_item['gsiK3SortKey']
    assert updated_trending_item['gsiA1SortKey'] == org_trending_item['gsiA1SortKey']


def test_increment_score_multiple_records_with_same_timestamp(trending_manager):
    item_type = trending_manager.enums.TrendingItemType.POST
    item_id = 'user-id'
    org_amount = 4
    update_amount = 5
    now = pendulum.now('utc')

    # create a trending item
    item = trending_manager.increment_score(item_type, item_id, amount=org_amount, now=now)
    assert item['pendingViewCount'] == 0

    # update the trending item
    item = trending_manager.increment_score(item_type, item_id, amount=update_amount, now=now)
    assert item['pendingViewCount'] == 0
    assert item['gsiK3SortKey'] == org_amount + update_amount


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


def test_reindex_all_operates_on_correct_items(trending_manager, user, post_manager):
    now = pendulum.now('utc')

    # add one user item now
    trending_manager.increment_score(TrendingItemType.USER, user.id, amount=42, now=now)

    # add one post item in the future a second
    post_id_1 = 'post-id-1'
    post_manager.add_post(user, post_id_1, PostType.TEXT_ONLY, text='t')
    viewed_at = now + pendulum.duration(seconds=1)
    trending_manager.increment_score(TrendingItemType.POST, post_id_1, amount=9, now=viewed_at)

    # add one post item a day ago, give it some pending views
    post_id_2 = 'post-id-2'
    post_manager.add_post(user, post_id_2, PostType.TEXT_ONLY, text='t')
    post_at_2 = now - pendulum.duration(days=1)
    trending_manager.increment_score(TrendingItemType.POST, post_id_2, amount=10, now=post_at_2)
    trending_manager.increment_score(TrendingItemType.POST, post_id_2, amount=5)

    # pull originals from db, save them
    org_user_items = list(trending_manager.dynamo.generate_trendings(TrendingItemType.USER))
    assert len(org_user_items) == 1
    assert org_user_items[0]['partitionKey'] == f'trending/{user.id}'

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


def test_reindex_deletes_as_needed_from_score_decay(trending_manager, post_manager, user):
    now = pendulum.now('utc')

    # add one post item viewed just over a day ago
    post_id_1 = 'post-id-over'
    post_manager.add_post(user, post_id_1, PostType.TEXT_ONLY, text='t')
    viewed_at = now - pendulum.duration(hours=25)
    trending_manager.increment_score(TrendingItemType.POST, post_id_1, amount=1, now=viewed_at)

    # add another post item viewed just under a day ago
    post_id_2 = 'post-id-under'
    post_manager.add_post(user, post_id_2, PostType.TEXT_ONLY, text='t')
    viewed_at = now - pendulum.duration(hours=23)
    trending_manager.increment_score(TrendingItemType.POST, post_id_2, amount=1, now=viewed_at)

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


def test_increment_scores_for_post(trending_manager, user, post_manager, real_user):
    # check initial state
    assert list(trending_manager.dynamo.generate_trendings('post')) == []
    assert list(trending_manager.dynamo.generate_trendings('user')) == []

    # verify no trending for non-original posts
    post = post_manager.add_post(user, str(uuid.uuid4()), PostType.TEXT_ONLY, text='t')
    post.item['originalPostId'] = 'pid-other'
    trending_manager.increment_scores_for_post(post)
    assert list(trending_manager.dynamo.generate_trendings('post')) == []
    assert list(trending_manager.dynamo.generate_trendings('user')) == []

    # verify no trending for post older than 24 hours
    posted_at = pendulum.now('utc') - pendulum.duration(hours=25)
    post = post_manager.add_post(user, str(uuid.uuid4()), PostType.TEXT_ONLY, text='t', now=posted_at)
    trending_manager.increment_scores_for_post(post)
    assert list(trending_manager.dynamo.generate_trendings('post')) == []
    assert list(trending_manager.dynamo.generate_trendings('user')) == []

    # verify no trending for posts that fail verification
    post = post_manager.add_post(real_user, str(uuid.uuid4()), PostType.TEXT_ONLY, text='t')
    trending_manager.increment_scores_for_post(post)
    assert list(trending_manager.dynamo.generate_trendings('post')) == []
    assert list(trending_manager.dynamo.generate_trendings('user')) == []

    # verify trending works for a normal post
    post = post_manager.add_post(user, str(uuid.uuid4()), PostType.TEXT_ONLY, text='t')
    trending_manager.increment_scores_for_post(post)
    assert [i['partitionKey'][9:] for i in trending_manager.dynamo.generate_trendings('post')] == [post.id]
    assert [i['partitionKey'][9:] for i in trending_manager.dynamo.generate_trendings('user')] == [user.id]
