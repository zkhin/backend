import logging
from unittest.mock import Mock, call

import pendulum
import pytest

from app.models.post.enums import PostStatus, PostType


@pytest.fixture
def posts(post_manager, user_manager):
    user = user_manager.create_cognito_only_user('pbuid', 'pbUname')
    post1 = post_manager.add_post(user.id, 'pid1', PostType.TEXT_ONLY, text='t')
    post2 = post_manager.add_post(user.id, 'pid2', PostType.TEXT_ONLY, text='t')
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
    viewed_at = pendulum.now('utc')
    post_view_manager.record_views('vuid', ['pid1', 'pid2', 'pid1'], viewed_at)
    assert post_view_manager.record_view.mock_calls == [
        call('vuid', 'pid1', 2, viewed_at),
        call('vuid', 'pid2', 1, viewed_at),
    ]


def test_record_view_post_not_completed(post_view_manager, posts, caplog):
    user_id = 'vuid'

    # set up an archived post
    post = posts[0]
    post.archive()

    # try to record a view on it
    with caplog.at_level(logging.WARNING):
        # fails with logged warning
        post_view_manager.record_view(user_id, post.id, 3, pendulum.now('utc'))

    # check the logging
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == 'WARNING'
    assert f'`{user_id}`' in caplog.records[0].msg
    assert f'`{post.id}`' in caplog.records[0].msg

    # check the viewedByCounts and the trending indexes did not change
    posted_by_user_id = post.item['postedByUserId']
    assert post_view_manager.post_manager.dynamo.get_post(post.id).get('viewedByCount', 0) == 0
    assert post_view_manager.user_manager.dynamo.get_user(posted_by_user_id).get('postViewedByCount', 0) == 0
    assert post_view_manager.trending_manager.dynamo.get_trending(post.id) is None
    assert post_view_manager.trending_manager.dynamo.get_trending(posted_by_user_id) is None


def test_record_view_post_does_not_exist(post_view_manager, caplog):
    user_id = 'vuid'
    post_id = 'pid-dne'

    with caplog.at_level(logging.WARNING):
        # fails with logged warning
        post_view_manager.record_view(user_id, post_id, 3, pendulum.now('utc'))

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
    viewed_at = pendulum.now('utc')
    viewed_at_str = viewed_at.to_iso8601_string()

    # check there is no post view yet recorded for this user on this post
    assert post_view_manager.dynamo.get_post_view(post_id, viewed_by_user_id) is None
    assert post_view_manager.post_manager.dynamo.get_post(post_id).get('viewedByCount', 0) == 0
    assert post_view_manager.user_manager.dynamo.get_user(posted_by_user_id).get('postViewedByCount', 0) == 0
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
    assert post_view_manager.post_manager.dynamo.get_post(post_id).get('viewedByCount', 0) == 1
    assert post_view_manager.user_manager.dynamo.get_user(posted_by_user_id).get('postViewedByCount', 0) == 1
    assert post_view_manager.trending_manager.dynamo.get_trending(post_id).get('gsiK3SortKey', 0) == 1
    assert post_view_manager.trending_manager.dynamo.get_trending(posted_by_user_id).get('gsiK3SortKey', 0) == 1

    # record a second post view for this user on this post
    new_view_count = 5
    new_viewed_at = pendulum.now('utc')
    new_viewed_at_str = new_viewed_at.to_iso8601_string()
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
    assert post_view_manager.post_manager.dynamo.get_post(post_id).get('viewedByCount', 0) == 1
    assert post_view_manager.user_manager.dynamo.get_user(posted_by_user_id).get('postViewedByCount', 0) == 1
    assert post_view_manager.trending_manager.dynamo.get_trending(post_id).get('gsiK3SortKey', 0) == 1
    assert post_view_manager.trending_manager.dynamo.get_trending(posted_by_user_id).get('gsiK3SortKey', 0) == 1


def test_record_view_by_post_owner_not_recorded(post_view_manager, dynamo_client, posts):
    post, _ = posts
    posted_by_user_id = post.item['postedByUserId']
    viewed_by_user_id = posted_by_user_id
    post_id = post.id
    view_count = 3
    viewed_at = pendulum.now('utc')

    # check there is no post view yet recorded for this user on this post
    assert post_view_manager.dynamo.get_post_view(post_id, viewed_by_user_id) is None
    assert post_view_manager.post_manager.dynamo.get_post(post_id).get('viewedByCount', 0) == 0
    assert post_view_manager.user_manager.dynamo.get_user(posted_by_user_id).get('postViewedByCount', 0) == 0
    assert post_view_manager.trending_manager.dynamo.get_trending(post_id) is None
    assert post_view_manager.trending_manager.dynamo.get_trending(posted_by_user_id) is None

    # record the first post view
    post_view_manager.record_view(viewed_by_user_id, post_id, view_count, viewed_at)

    # check nothing changed in the DB
    assert post_view_manager.dynamo.get_post_view(post_id, viewed_by_user_id) is None
    assert post_view_manager.post_manager.dynamo.get_post(post_id).get('viewedByCount', 0) == 0
    assert post_view_manager.user_manager.dynamo.get_user(posted_by_user_id).get('postViewedByCount', 0) == 0
    assert post_view_manager.trending_manager.dynamo.get_trending(post_id) is None
    assert post_view_manager.trending_manager.dynamo.get_trending(posted_by_user_id) is None


def test_record_view_for_non_original_post(post_view_manager, dynamo_client, posts):
    post_dynamo = post_view_manager.post_manager.dynamo
    org_post, non_org_post = posts

    # hack to get these text-only posts to have an original. Set it back to pending and then completed
    dynamo_client.transact_write_items([
        post_dynamo.transact_set_post_status(non_org_post.item, PostStatus.PENDING),
    ])
    dynamo_client.transact_write_items([
        post_dynamo.transact_set_post_status(non_org_post.item, PostStatus.COMPLETED, original_post_id=org_post.id),
    ])
    non_org_post.refresh_item()

    viewed_by_user_id = 'vuid'
    posted_by_user_id = org_post.item['postedByUserId']
    org_post_id = org_post.id
    non_org_post_id = non_org_post.id
    view_count = 3
    viewed_at = pendulum.now('utc')
    viewed_at_str = viewed_at.to_iso8601_string()

    # check there is no post view yet recorded for this user on either post
    assert post_view_manager.dynamo.get_post_view(org_post_id, viewed_by_user_id) is None
    assert post_view_manager.dynamo.get_post_view(non_org_post_id, viewed_by_user_id) is None
    assert post_view_manager.post_manager.dynamo.get_post(org_post_id).get('viewedByCount', 0) == 0
    assert post_view_manager.post_manager.dynamo.get_post(non_org_post_id).get('viewedByCount', 0) == 0
    assert post_view_manager.user_manager.dynamo.get_user(posted_by_user_id).get('postViewedByCount', 0) == 0
    assert post_view_manager.trending_manager.dynamo.get_trending(org_post_id) is None
    assert post_view_manager.trending_manager.dynamo.get_trending(non_org_post_id) is None
    assert post_view_manager.trending_manager.dynamo.get_trending(posted_by_user_id) is None

    # record a first post view on the non-original post
    post_view_manager.record_view(viewed_by_user_id, non_org_post_id, view_count, viewed_at)

    # check two post view items were created, one for each post
    item = post_view_manager.dynamo.get_post_view(org_post_id, viewed_by_user_id)
    assert item['postId'] == org_post_id
    assert item['viewedByUserId'] == viewed_by_user_id
    assert item['viewCount'] == view_count
    assert item['firstViewedAt'] == viewed_at_str
    assert item['lastViewedAt'] == viewed_at_str
    non_org_item = post_view_manager.dynamo.get_post_view(non_org_post_id, viewed_by_user_id)
    assert non_org_item['postId'] == non_org_post_id
    assert non_org_item['viewedByUserId'] == viewed_by_user_id
    assert non_org_item['viewCount'] == view_count
    assert non_org_item['firstViewedAt'] == viewed_at_str
    assert non_org_item['lastViewedAt'] == viewed_at_str

    # check the viewedByCounts
    assert post_view_manager.post_manager.dynamo.get_post(org_post_id).get('viewedByCount', 0) == 1
    assert post_view_manager.post_manager.dynamo.get_post(non_org_post_id).get('viewedByCount', 0) == 1
    assert post_view_manager.user_manager.dynamo.get_user(posted_by_user_id).get('postViewedByCount', 0) == 2

    # check the original post made it into the trending indexes, and then non-original did not
    assert post_view_manager.trending_manager.dynamo.get_trending(org_post_id).get('gsiK3SortKey', 0) == 1
    assert post_view_manager.trending_manager.dynamo.get_trending(non_org_post_id) is None
    assert post_view_manager.trending_manager.dynamo.get_trending(posted_by_user_id).get('gsiK3SortKey', 0) == 1

    # now record a view directly on the original post
    new_view_count = 5
    new_viewed_at = pendulum.now('utc')
    new_viewed_at_str = new_viewed_at.to_iso8601_string()
    post_view_manager.record_view(viewed_by_user_id, org_post_id, new_view_count, new_viewed_at)

    # check the post view item for the original post was incremented correctly
    item = post_view_manager.dynamo.get_post_view(org_post_id, viewed_by_user_id)
    assert item['postId'] == org_post_id
    assert item['viewedByUserId'] == viewed_by_user_id
    assert item['viewCount'] == view_count + new_view_count
    assert item['firstViewedAt'] == viewed_at_str
    assert item['lastViewedAt'] == new_viewed_at_str

    # no change for the non-original post
    assert post_view_manager.dynamo.get_post_view(non_org_post_id, viewed_by_user_id) == non_org_item

    # check no change to viewedByCounts, nor trending indexes
    assert post_view_manager.post_manager.dynamo.get_post(org_post_id).get('viewedByCount', 0) == 1
    assert post_view_manager.post_manager.dynamo.get_post(non_org_post_id).get('viewedByCount', 0) == 1
    assert post_view_manager.user_manager.dynamo.get_user(posted_by_user_id).get('postViewedByCount', 0) == 2
    assert post_view_manager.trending_manager.dynamo.get_trending(org_post_id).get('gsiK3SortKey', 0) == 1
    assert post_view_manager.trending_manager.dynamo.get_trending(non_org_post_id) is None
    assert post_view_manager.trending_manager.dynamo.get_trending(posted_by_user_id).get('gsiK3SortKey', 0) == 1
