import pendulum
import pytest

from app.models.feed.dynamo import FeedDynamo


@pytest.fixture
def feed_dynamo(dynamo_client):
    yield FeedDynamo(dynamo_client)


def test_build_pk(feed_dynamo):
    pk = feed_dynamo.build_pk('uid', 'pid')
    assert pk == {
        'partitionKey': 'feed/uid/pid',
        'sortKey': '-',
    }


def test_parse_pk(feed_dynamo):
    user_id, post_id = feed_dynamo.parse_pk({'partitionKey': 'feed/uid/pid', 'sortKey': '-',})
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
        'partitionKey': 'feed/fuid/pid',
        'sortKey': '-',
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
            {'postId': 'pid1', 'postedByUserId': 'pbuid', 'postedAt': posted_at,},
            {'postId': 'pid2', 'postedByUserId': 'pbuid', 'postedAt': posted_at,},
        ]
    )
    feed_dynamo.add_posts_to_feed(user_id, posts_generator)

    # check those two posts are in the feed
    feed = list(feed_dynamo.generate_feed(user_id))
    assert sorted([f['postId'] for f in feed]) == ['pid1', 'pid2']

    # add another post to the feed
    posted_at = pendulum.now('utc').to_iso8601_string()
    posts_generator = iter([{'postId': 'pid3', 'postedByUserId': 'pbuid', 'postedAt': posted_at,}])
    feed_dynamo.add_posts_to_feed(user_id, posts_generator)

    # check all three posts are in the feed
    feed = list(feed_dynamo.generate_feed(user_id))
    assert sorted([f['postId'] for f in feed]) == ['pid1', 'pid2', 'pid3']


def test_delete_posts_from_feed(feed_dynamo):
    user_id = 'fuid'

    # check nothing in feed
    assert list(feed_dynamo.generate_feed(user_id)) == []

    # delete post that doesn't exist, no error thrown
    post_id_generator = iter(['p-dne'])
    feed_dynamo.delete_posts_from_feed(user_id, post_id_generator)

    # check nothing in feed
    assert list(feed_dynamo.generate_feed(user_id)) == []

    # add three posts to the feed
    posted_at = pendulum.now('utc').to_iso8601_string()
    posts_generator = iter(
        [
            {'postId': 'pid1', 'postedByUserId': 'pbuid', 'postedAt': posted_at,},
            {'postId': 'pid2', 'postedByUserId': 'pbuid', 'postedAt': posted_at,},
            {'postId': 'pid3', 'postedByUserId': 'pbuid', 'postedAt': posted_at,},
        ]
    )
    feed_dynamo.add_posts_to_feed(user_id, posts_generator)

    # check those three posts are in the feed
    feed = list(feed_dynamo.generate_feed(user_id))
    assert sorted([f['postId'] for f in feed]) == ['pid1', 'pid2', 'pid3']

    # delete nothing
    post_id_generator = iter([])
    feed_dynamo.delete_posts_from_feed(user_id, post_id_generator)

    # check those three posts are in the feed
    feed = list(feed_dynamo.generate_feed(user_id))
    assert sorted([f['postId'] for f in feed]) == ['pid1', 'pid2', 'pid3']

    # delete two posts
    post_id_generator = iter(['pid3', 'pid1'])
    feed_dynamo.delete_posts_from_feed(user_id, post_id_generator)

    # check one post left in feed
    feed = list(feed_dynamo.generate_feed(user_id))
    assert sorted([f['postId'] for f in feed]) == ['pid2']

    # delete that post
    post_id_generator = iter(['pid2'])
    feed_dynamo.delete_posts_from_feed(user_id, post_id_generator)

    # check nothing in feed
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


def test_delete_post_from_feeds(feed_dynamo):
    feed_uids = ['fuid1', 'fuid2']

    # delete post from no feeds - verify no error
    feed_dynamo.delete_post_from_feeds(iter([]), 'pid')

    # delete post from feeds where it doesn't exist - verify no error
    feed_dynamo.delete_post_from_feeds(iter(['fuid']), 'pid')

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
    feed_dynamo.delete_post_from_feeds(iter(feed_uids), 'pid3')

    # verify the two feeds look as expected
    assert [f['postId'] for f in feed_dynamo.generate_feed(feed_uids[0])] == ['pid2']
    assert [f['postId'] for f in feed_dynamo.generate_feed(feed_uids[1])] == []

    # delete the other post from the feeds
    feed_dynamo.delete_post_from_feeds(iter(feed_uids), 'pid2')

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
        {'postId': 'pid1', 'postedByUserId': pb_user_id_1, 'postedAt': posted_at,},
        {'postId': 'pid2', 'postedByUserId': pb_user_id_2, 'postedAt': posted_at,},
        {'postId': 'pid3', 'postedByUserId': pb_user_id_1, 'postedAt': posted_at,},
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
