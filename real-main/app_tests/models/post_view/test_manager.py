from datetime import datetime
import logging
from unittest.mock import Mock, call

import pytest


@pytest.fixture
def posts(post_manager, user_manager):
    user = user_manager.create_cognito_only_user('pbuid', 'pbUname')
    post1 = post_manager.add_post(user.id, 'pid1', text='t')
    post2 = post_manager.add_post(user.id, 'pid2', text='t')
    yield (post1, post2)


def test_delete_all_for_post(post_view_manager, posts):
    post1, post2 = posts
    vb_user_id_1 = 'vuid1'
    vb_user_id_2 = 'vuid2'

    # check post2 have no views
    assert list(post_view_manager.dynamo.generate_post_views(post1.id)) == []
    assert list(post_view_manager.dynamo.generate_post_views(post2.id)) == []

    # delete all for post that has none, check
    post_view_manager.delete_all_for_post(post1.id)
    assert list(post_view_manager.dynamo.generate_post_views(post1.id)) == []

    # record two views on each of them
    post_view_manager.record_views(vb_user_id_1, [post1.id, post2.id])
    post_view_manager.record_views(vb_user_id_2, [post1.id, post2.id])

    # check db
    vuids = [vb_user_id_1, vb_user_id_2]
    assert sorted([pv['viewedByUserId'] for pv in post_view_manager.dynamo.generate_post_views(post1.id)]) == vuids
    assert sorted([pv['viewedByUserId'] for pv in post_view_manager.dynamo.generate_post_views(post2.id)]) == vuids

    # delete all views on one post, check again
    post_view_manager.delete_all_for_post(post1.id)
    assert list(post_view_manager.dynamo.generate_post_views(post1.id)) == []
    assert sorted([pv['viewedByUserId'] for pv in post_view_manager.dynamo.generate_post_views(post2.id)]) == vuids

    # delete all views on the other post, check again
    post_view_manager.delete_all_for_post(post2.id)
    assert list(post_view_manager.dynamo.generate_post_views(post1.id)) == []
    assert list(post_view_manager.dynamo.generate_post_views(post2.id)) == []


def test_record_views(post_view_manager):
    # catch any calls to 'record_view'
    post_view_manager.record_view = Mock()

    # call with no post_ids
    post_view_manager.record_views('vuid', [])
    assert post_view_manager.record_view.mock_calls == []

    # call with some post ids
    viewed_at = datetime.utcnow()
    post_view_manager.record_views('vuid', ['pid1', 'pid2', 'pid1'], viewed_at)
    assert post_view_manager.record_view.mock_calls == [
        call('vuid', 'pid1', 2, viewed_at),
        call('vuid', 'pid2', 1, viewed_at),
    ]


def test_record_view_post_does_not_exist(post_view_manager, caplog):
    user_id = 'vuid'
    post_id = 'pid-dne'

    with caplog.at_level(logging.WARNING):
        # fails with logged warning
        post_view_manager.record_view(user_id, post_id, 3, datetime.utcnow())

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == 'WARNING'
    assert f'`{user_id}`' in caplog.records[0].msg
    assert f'`{post_id}`' in caplog.records[0].msg


def test_record_view(post_view_manager, dynamo_client, posts):
    post, _ = posts
    viewed_by_user_id = 'vuid'
    posted_by_user_id = post.item['postedByUserId']
    post_id = post.id
    view_count = 3
    viewed_at = datetime.utcnow()
    viewed_at_str = viewed_at.isoformat() + 'Z'

    # check there is no post view yet recorded for this user on this post
    assert post_view_manager.dynamo.get_post_view(post_id, viewed_by_user_id) is None
    assert post_view_manager.post_dynamo.get_post(post_id).get('viewedByCount', 0) == 0
    assert post_view_manager.user_dynamo.get_user(posted_by_user_id).get('postViewedByCount', 0) == 0
    assert post_view_manager.trending_manager.dynamo.get_trending(post_id) is None
    assert post_view_manager.trending_manager.dynamo.get_trending(posted_by_user_id) is None

    # record the first post view
    post_view_manager.record_view(viewed_by_user_id, post_id, view_count, viewed_at)

    # check the post view item exists and has the right deets
    item = post_view_manager.dynamo.get_post_view(post_id, viewed_by_user_id)
    assert item['postId'] == post_id
    assert item['postedByUserId'] == posted_by_user_id
    assert item['viewedByUserId'] == viewed_by_user_id
    assert item['viewCount'] == view_count
    assert item['firstViewedAt'] == viewed_at_str
    assert item['lastViewedAt'] == viewed_at_str

    # check the viewedByCounts and the trending indexes all incremented
    assert post_view_manager.post_dynamo.get_post(post_id).get('viewedByCount', 0) == 1
    assert post_view_manager.user_dynamo.get_user(posted_by_user_id).get('postViewedByCount', 0) == 1
    assert post_view_manager.trending_manager.dynamo.get_trending(post_id).get('gsiK3SortKey', 0) == 1
    assert post_view_manager.trending_manager.dynamo.get_trending(posted_by_user_id).get('gsiK3SortKey', 0) == 1

    # record a second post view for this user on this post
    new_view_count = 5
    new_viewed_at = datetime.utcnow()
    new_viewed_at_str = new_viewed_at.isoformat() + 'Z'
    post_view_manager.record_view(viewed_by_user_id, post_id, new_view_count, new_viewed_at)

    # check the post view item exists and has the right deets
    item = post_view_manager.dynamo.get_post_view(post_id, viewed_by_user_id)
    assert item['postId'] == post_id
    assert item['postedByUserId'] == posted_by_user_id
    assert item['viewedByUserId'] == viewed_by_user_id
    assert item['viewCount'] == view_count + new_view_count
    assert item['firstViewedAt'] == viewed_at_str
    assert item['lastViewedAt'] == new_viewed_at_str

    # check the viewedByCounts and the trending indexes all did not change
    assert post_view_manager.post_dynamo.get_post(post_id).get('viewedByCount', 0) == 1
    assert post_view_manager.user_dynamo.get_user(posted_by_user_id).get('postViewedByCount', 0) == 1
    assert post_view_manager.trending_manager.dynamo.get_trending(post_id).get('gsiK3SortKey', 0) == 1
    assert post_view_manager.trending_manager.dynamo.get_trending(posted_by_user_id).get('gsiK3SortKey', 0) == 1
