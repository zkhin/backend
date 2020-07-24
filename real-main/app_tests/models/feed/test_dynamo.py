import pendulum
import pytest

from app.models.feed.dynamo import FeedDynamo


@pytest.fixture
def feed_dynamo(dynamo_client):
    yield FeedDynamo(dynamo_client)


def test_build_pk(feed_dynamo):
    pk = feed_dynamo.build_pk('uid', 'pid')
    assert pk == {
        'partitionKey': 'user/uid',
        'sortKey': 'feed/pid',
    }


def test_parse_pk(feed_dynamo):
    user_id, post_id = feed_dynamo.parse_pk({'partitionKey': 'user/uid', 'sortKey': 'feed/pid'})
    assert user_id == 'uid'
    assert post_id == 'pid'


def test_build_item(feed_dynamo):
    feed_user_id = 'fuid'
    posted_at = pendulum.now('utc').to_iso8601_string()
    post_item = {
        'postId': 'pid',
        'postedByUserId': 'pbuid',
        'postedAt': posted_at,
    }
    feed_item = feed_dynamo.build_item(feed_user_id, post_item)
    assert feed_item == {
        'schemaVersion': 2,
        'partitionKey': 'user/fuid',
        'sortKey': 'feed/pid',
        'gsiA1PartitionKey': 'feed/fuid',
        'gsiA1SortKey': posted_at,
        'userId': 'fuid',
        'postId': 'pid',
        'postedAt': posted_at,
        'postedByUserId': 'pbuid',
        'gsiK2PartitionKey': 'feed/fuid/pbuid',
        'gsiK2SortKey': posted_at,
    }


def test_add_posts_to_feed(feed_dynamo):
    user_id = 'fuid'

    # check nothing in feed
    assert list(feed_dynamo.generate_feed(user_id)) == []

    # add nothing to feed
    posts_generator = iter([])
    feed_dynamo.add_posts_to_feed(user_id, posts_generator)

    # check nothing in feed
    assert list(feed_dynamo.generate_feed(user_id)) == []

    # add two posts to the feed
    posted_at = pendulum.now('utc').to_iso8601_string()
    posts_generator = iter(
        [
            {'postId': 'pid1', 'postedByUserId': 'pbuid', 'postedAt': posted_at},
            {'postId': 'pid2', 'postedByUserId': 'pbuid', 'postedAt': posted_at},
        ]
    )
    feed_dynamo.add_posts_to_feed(user_id, posts_generator)

    # check those two posts are in the feed
    feed = list(feed_dynamo.generate_feed(user_id))
    assert sorted([f['postId'] for f in feed]) == ['pid1', 'pid2']

    # add another post to the feed
    posted_at = pendulum.now('utc').to_iso8601_string()
    posts_generator = iter([{'postId': 'pid3', 'postedByUserId': 'pbuid', 'postedAt': posted_at}])
    feed_dynamo.add_posts_to_feed(user_id, posts_generator)

    # check all three posts are in the feed
    feed = list(feed_dynamo.generate_feed(user_id))
    assert sorted([f['postId'] for f in feed]) == ['pid1', 'pid2', 'pid3']


def test_delete_by_post_owner(feed_dynamo):
    user_id = 'fuid'
    assert list(feed_dynamo.generate_feed(user_id)) == []

    # check no-op doesn't error, verify state
    feed_dynamo.delete_by_post_owner(user_id, 'pbuid')
    assert list(feed_dynamo.generate_feed(user_id)) == []

    # add three posts to the feed, verify
    posted_at = pendulum.now('utc').to_iso8601_string()
    posts_generator = iter(
        [
            {'postId': 'pid1', 'postedByUserId': 'pbuid', 'postedAt': posted_at},
            {'postId': 'pid2', 'postedByUserId': 'other-uid', 'postedAt': posted_at},
            {'postId': 'pid3', 'postedByUserId': 'pbuid', 'postedAt': posted_at},
            {'postId': 'pid4', 'postedByUserId': 'pbuid', 'postedAt': posted_at},
        ]
    )
    feed_dynamo.add_posts_to_feed(user_id, posts_generator)
    feed = list(feed_dynamo.generate_feed(user_id))
    assert sorted([f['postId'] for f in feed]) == ['pid1', 'pid2', 'pid3', 'pid4']

    # delete three posts, verify
    feed_dynamo.delete_by_post_owner(user_id, 'pbuid')
    feed = list(feed_dynamo.generate_feed(user_id))
    assert sorted([f['postId'] for f in feed]) == ['pid2']

    # delete last post, verify
    feed_dynamo.delete_by_post_owner(user_id, 'other-uid')
    assert list(feed_dynamo.generate_feed(user_id)) == []


def test_add_post_to_feeds(feed_dynamo):
    feed_uids = ['fuid1', 'fuid2']

    # check nothing in feeds
    assert list(feed_dynamo.generate_feed(feed_uids[0])) == []
    assert list(feed_dynamo.generate_feed(feed_uids[1])) == []

    # add post to no feeds - verify no error
    posted_at = pendulum.now('utc').to_iso8601_string()
    post_item = {
        'postId': 'pid3',
        'postedByUserId': 'pbuid',
        'postedAt': posted_at,
    }
    feed_dynamo.add_post_to_feeds(iter([]), post_item)

    # add post to the feeds
    feed_dynamo.add_post_to_feeds(iter(feed_uids), post_item)

    # check the feeds are as expected
    assert [f['postId'] for f in feed_dynamo.generate_feed(feed_uids[0])] == ['pid3']
    assert [f['postId'] for f in feed_dynamo.generate_feed(feed_uids[1])] == ['pid3']

    # add noather post to the feeds
    posted_at = pendulum.now('utc').to_iso8601_string()
    post_item = {
        'postId': 'pid2',
        'postedByUserId': 'pbuid',
        'postedAt': posted_at,
    }
    feed_dynamo.add_post_to_feeds(iter(feed_uids), post_item)

    # check the feeds are as expected
    assert sorted([f['postId'] for f in feed_dynamo.generate_feed(feed_uids[0])]) == ['pid2', 'pid3']
    assert sorted([f['postId'] for f in feed_dynamo.generate_feed(feed_uids[1])]) == ['pid2', 'pid3']


def test_delete_by_post(feed_dynamo):
    feed_uids = ['fuid1', 'fuid2']

    # delete post from no feeds - verify no error
    feed_dynamo.delete_by_post('pid', iter([]))

    # delete post from feeds where it doesn't exist - verify no error
    feed_dynamo.delete_by_post('pid', iter(['fuid']))

    # add a post to two feeds
    posted_at = pendulum.now('utc').to_iso8601_string()
    post_item = {
        'postId': 'pid3',
        'postedByUserId': 'pbuid',
        'postedAt': posted_at,
    }
    feed_dynamo.add_post_to_feeds(iter(feed_uids), post_item)

    # add another post to one of the feeds
    post_item = {
        'postId': 'pid2',
        'postedByUserId': 'pbuid',
        'postedAt': posted_at,
    }
    feed_dynamo.add_post_to_feeds(iter([feed_uids[0]]), post_item)

    # verify the two feeds look as expected
    assert sorted([f['postId'] for f in feed_dynamo.generate_feed(feed_uids[0])]) == ['pid2', 'pid3']
    assert [f['postId'] for f in feed_dynamo.generate_feed(feed_uids[1])] == ['pid3']

    # delete a post from the feeds
    feed_dynamo.delete_by_post('pid3', iter(feed_uids))

    # verify the two feeds look as expected
    assert [f['postId'] for f in feed_dynamo.generate_feed(feed_uids[0])] == ['pid2']
    assert [f['postId'] for f in feed_dynamo.generate_feed(feed_uids[1])] == []

    # delete the other post from the feeds
    feed_dynamo.delete_by_post('pid2', iter(feed_uids))

    # verify the two feeds look as expected
    assert [f['postId'] for f in feed_dynamo.generate_feed(feed_uids[0])] == []
    assert [f['postId'] for f in feed_dynamo.generate_feed(feed_uids[1])] == []


def test_generate_feed_pks_by_posted_by_user(feed_dynamo):
    feed_user_id = 'fuid'
    pb_user_id_1 = 'pbuid1'
    pb_user_id_2 = 'pbuid2'

    # add three posts by different users to the feed
    posted_at = pendulum.now('utc').to_iso8601_string()
    post_items = [
        {'postId': 'pid1', 'postedByUserId': pb_user_id_1, 'postedAt': posted_at},
        {'postId': 'pid2', 'postedByUserId': pb_user_id_2, 'postedAt': posted_at},
        {'postId': 'pid3', 'postedByUserId': pb_user_id_1, 'postedAt': posted_at},
    ]
    feed_dynamo.add_posts_to_feed(feed_user_id, iter(post_items))

    # verify the feed looks as expected
    assert sorted([f['postId'] for f in feed_dynamo.generate_feed(feed_user_id)]) == ['pid1', 'pid2', 'pid3']

    # verify we can generate items in the feed by who posted them
    feed_pk_gen = feed_dynamo.generate_feed_pks_by_posted_by_user(feed_user_id, pb_user_id_1)
    assert sorted([feed_dynamo.parse_pk(fpk)[1] for fpk in feed_pk_gen]) == ['pid1', 'pid3']

    feed_pk_gen = feed_dynamo.generate_feed_pks_by_posted_by_user(feed_user_id, pb_user_id_2)
    assert [feed_dynamo.parse_pk(fpk)[1] for fpk in feed_pk_gen] == ['pid2']

    # check we correctly handle a user that has posted no posts to the feed
    assert list(feed_dynamo.generate_feed_pks_by_posted_by_user(feed_user_id, 'other-uid')) == []
