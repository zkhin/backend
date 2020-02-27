import pendulum
import pytest

from app.models.post.enums import PostType
from app.models.post_view.dynamo import PostViewDynamo
from app.models.post_view.exceptions import PostViewAlreadyExists, PostViewDoesNotExist


@pytest.fixture
def post_view_dynamo(dynamo_client):
    yield PostViewDynamo(dynamo_client)


@pytest.fixture
def posts(post_manager, user_manager):
    user = user_manager.create_cognito_only_user('pbuid', 'pbUname')
    post1 = post_manager.add_post(user.id, 'pid1', PostType.TEXT_ONLY, text='t')
    post2 = post_manager.add_post(user.id, 'pid2', PostType.TEXT_ONLY, text='t')
    yield (post1, post2)


def test_get_post_view_does_not_exist(post_view_dynamo):
    resp = post_view_dynamo.get_post_view('piddne', 'uid')
    assert resp is None


def test_get_post_view_strongly_consistent(post_view_dynamo):
    post_id = 'pid'
    user_id = 'uid'
    post_item = {
        'postId': post_id,
        'postedByUserId': 'pbuid',
    }

    # add a post view, read it back
    post_view_dynamo.add_post_view(post_item, user_id, 1, pendulum.now('utc'))
    resp = post_view_dynamo.get_post_view(post_id, user_id, strongly_consistent=True)
    assert resp is not None


def test_add_post_view(post_view_dynamo):
    post_id = 'pid'
    user_id = 'uid'
    post_item = {
        'postId': post_id,
        'postedByUserId': 'pbuid',
    }
    view_count = 2
    viewed_at = pendulum.now('utc')

    # add the post view, check the format is correct
    post_view_item = post_view_dynamo.add_post_view(post_item, user_id, view_count, viewed_at)
    viewed_at_str = viewed_at.to_iso8601_string()
    assert post_view_item == {
        'partitionKey': 'postView/pid/uid',
        'sortKey': '-',
        'schemaVersion': 0,
        'gsiA1PartitionKey': 'postView/pid',
        'gsiA1SortKey': viewed_at_str,
        'postId': 'pid',
        'postedByUserId': 'pbuid',
        'viewedByUserId': 'uid',
        'viewCount': 2,
        'firstViewedAt': viewed_at_str,
        'lastViewedAt': viewed_at_str,
    }

    # make sure it really saved in the DB
    post_view_item_db = post_view_dynamo.get_post_view(post_id, user_id)
    assert post_view_item_db == post_view_item


def test_add_post_view_already_exists(post_view_dynamo):
    post_id = 'pid'
    user_id = 'uid'
    post_item = {
        'postId': post_id,
        'postedByUserId': 'pbuid',
    }

    # add the post view, then try to add it again
    post_view_dynamo.add_post_view(post_item, user_id, 1, pendulum.now('utc'))
    with pytest.raises(PostViewAlreadyExists):
        post_view_dynamo.add_post_view(post_item, user_id, 1, pendulum.now('utc'))


def test_add_views_to_post_view(post_view_dynamo):
    post_id = 'pid'
    user_id = 'uid'
    post_item = {
        'postId': post_id,
        'postedByUserId': 'pbuid',
    }
    viewed_at = pendulum.now('utc')

    # create a post view, verify it has the values we expect
    item = post_view_dynamo.add_post_view(post_item, user_id, 2, viewed_at)
    assert item['postId'] == post_id
    assert item['viewedByUserId'] == user_id
    assert item['lastViewedAt'] == viewed_at.to_iso8601_string()
    assert item['viewCount'] == 2

    # update it, verify values changed correctly
    new_viewed_at = pendulum.now('utc')
    new_item = post_view_dynamo.add_views_to_post_view(post_id, user_id, 3, new_viewed_at)
    assert new_item['postId'] == post_id
    assert new_item['viewedByUserId'] == user_id
    assert new_item['lastViewedAt'] == new_viewed_at.to_iso8601_string()
    assert new_item['viewCount'] == 5

    # verify nothing changed except the values we expect
    new_item['lastViewedAt'] = item['lastViewedAt']
    new_item['viewCount'] = item['viewCount']
    assert new_item == item


def test_add_views_to_post_view_does_not_exist(post_view_dynamo):
    with pytest.raises(PostViewDoesNotExist):
        post_view_dynamo.add_views_to_post_view('pid', 'uid', 3, pendulum.now('utc'))


def test_generate_post_views(post_view_dynamo, dynamo_client, posts):
    post1, post2 = posts

    # add two post views of one of them
    post_view_dynamo.add_post_view(post1.item, 'uid1', 1, pendulum.now('utc'))
    post_view_dynamo.add_post_view(post1.item, 'uid2', 1, pendulum.now('utc'))

    # generate post views of both, check
    assert list(post_view_dynamo.generate_post_views(post2.id)) == []
    viewed_uids = [pv['viewedByUserId'] for pv in post_view_dynamo.generate_post_views(post1.id)]
    assert sorted(viewed_uids) == ['uid1', 'uid2']

    # add a post view of the other post, check generation of it
    post_view_dynamo.add_post_view(post2.item, 'uid1', 1, pendulum.now('utc'))
    viewed_uids = [pv['viewedByUserId'] for pv in post_view_dynamo.generate_post_views(post2.id)]
    assert sorted(viewed_uids) == ['uid1']


def test_delete_post_views(post_view_dynamo, dynamo_client, posts):
    post1, post2 = posts

    # add two post views of one of them, one view of the other
    pv_1 = post_view_dynamo.add_post_view(post1.item, 'uid1', 1, pendulum.now('utc'))
    pv_2 = post_view_dynamo.add_post_view(post1.item, 'uid2', 1, pendulum.now('utc'))
    pv_3 = post_view_dynamo.add_post_view(post2.item, 'uid1', 1, pendulum.now('utc'))

    # check generation
    viewed_uids = [pv['viewedByUserId'] for pv in post_view_dynamo.generate_post_views(post1.id)]
    assert sorted(viewed_uids) == ['uid1', 'uid2']
    viewed_uids = [pv['viewedByUserId'] for pv in post_view_dynamo.generate_post_views(post2.id)]
    assert sorted(viewed_uids) == ['uid1']

    # delete two posts views, one from each post
    post_view_dynamo.delete_post_views(iter([pv_1, pv_3]))

    # check generation
    viewed_uids = [pv['viewedByUserId'] for pv in post_view_dynamo.generate_post_views(post1.id)]
    assert sorted(viewed_uids) == ['uid2']
    viewed_uids = [pv['viewedByUserId'] for pv in post_view_dynamo.generate_post_views(post2.id)]
    assert sorted(viewed_uids) == []

    # delete the other post view
    post_view_dynamo.delete_post_views(iter([pv_2]))

    # check generation
    viewed_uids = [pv['viewedByUserId'] for pv in post_view_dynamo.generate_post_views(post1.id)]
    assert sorted(viewed_uids) == []
