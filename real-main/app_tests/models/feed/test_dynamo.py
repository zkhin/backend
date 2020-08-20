from uuid import uuid4

import pendulum
import pytest

from app.models.feed.dynamo import FeedDynamo


@pytest.fixture
def feed_dynamo(dynamo_client, dynamo_feed_client):
    yield FeedDynamo(dynamo_client, dynamo_feed_client)


def test_build_pk(feed_dynamo):
    pk = feed_dynamo.build_pk('uid', 'pid')
    assert pk == {
        'partitionKey': 'post/pid',
        'sortKey': 'feed/uid',
    }


def test_parse_pk(feed_dynamo):
    post_id, user_id = feed_dynamo.parse_pk({'partitionKey': 'post/pid', 'sortKey': 'feed/uid'})
    assert post_id == 'pid'
    assert user_id == 'uid'


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
        'schemaVersion': 3,
        'partitionKey': 'post/pid',
        'sortKey': 'feed/fuid',
        'gsiA1PartitionKey': 'feed/fuid',
        'gsiA1SortKey': posted_at,
        'gsiA2PartitionKey': 'feed/fuid',
        'gsiA2SortKey': 'pbuid',
    }


def test_item(feed_dynamo):
    feed_user_id = str(uuid4())
    post_id = str(uuid4())
    posted_at = pendulum.now('utc').to_iso8601_string()
    posted_by_user_id = str(uuid4())
    post_item = {
        'postId': post_id,
        'postedAt': posted_at,
        'postedByUserId': posted_by_user_id,
    }
    assert feed_dynamo.item(feed_user_id, post_item) == {
        'feedUserId': feed_user_id,
        'postId': post_id,
        'postedAt': posted_at,
        'postedByUserId': posted_by_user_id,
    }


def test_add_posts_to_feed(feed_dynamo):
    user_id = str(uuid4())

    # check nothing in feed
    assert list(feed_dynamo.generate_feed(user_id)) == []
    assert list(feed_dynamo.generate_items(user_id)) == []

    # add nothing to feed
    posts_generator = iter([])
    feed_dynamo.add_posts_to_feed(user_id, posts_generator)

    # check nothing in feed
    assert list(feed_dynamo.generate_feed(user_id)) == []
    assert list(feed_dynamo.generate_items(user_id)) == []

    # add two posts to the feed
    posted_at = pendulum.now('utc').to_iso8601_string()
    post_id_1, post_id_2 = str(uuid4()), str(uuid4())
    posts_generator = iter(
        [
            {'postId': post_id_1, 'postedByUserId': str(uuid4()), 'postedAt': posted_at},
            {'postId': post_id_2, 'postedByUserId': str(uuid4()), 'postedAt': posted_at},
        ]
    )
    feed_dynamo.add_posts_to_feed(user_id, posts_generator)

    # check those two posts are in the feed
    feed = list(feed_dynamo.generate_feed(user_id))
    assert sorted([f['partitionKey'] for f in feed]) == sorted([f'post/{post_id_1}', f'post/{post_id_2}'])
    items = list(feed_dynamo.generate_items(user_id))
    assert sorted([i['postId'] for i in items]) == sorted([post_id_1, post_id_2])

    # add another post to the feed
    posted_at = pendulum.now('utc').to_iso8601_string()
    post_id_3 = str(uuid4())
    posts_generator = iter([{'postId': post_id_3, 'postedByUserId': str(uuid4()), 'postedAt': posted_at}])
    feed_dynamo.add_posts_to_feed(user_id, posts_generator)

    # check all three posts are in the feed
    feed = list(feed_dynamo.generate_feed(user_id))
    assert sorted([f['partitionKey'] for f in feed]) == sorted(
        [f'post/{post_id_1}', f'post/{post_id_2}', f'post/{post_id_3}']
    )
    items = list(feed_dynamo.generate_items(user_id))
    assert sorted([i['postId'] for i in items]) == sorted([post_id_1, post_id_2, post_id_3])


def test_delete_by_post_owner(feed_dynamo):
    user_id = str(uuid4())
    assert list(feed_dynamo.generate_feed(user_id)) == []
    assert list(feed_dynamo.generate_items(user_id)) == []

    # check no-op doesn't error, verify state
    feed_dynamo.delete_by_post_owner(user_id, str(uuid4()))
    assert list(feed_dynamo.generate_feed(user_id)) == []
    assert list(feed_dynamo.generate_items(user_id)) == []

    # add three posts to the feed, verify
    posted_at = pendulum.now('utc').to_iso8601_string()
    pb_user_id, opb_user_id = str(uuid4()), str(uuid4())
    pid1, pid2, pid3, pid4 = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
    posts_generator = iter(
        [
            {'postId': pid1, 'postedByUserId': pb_user_id, 'postedAt': posted_at},
            {'postId': pid2, 'postedByUserId': opb_user_id, 'postedAt': posted_at},
            {'postId': pid3, 'postedByUserId': pb_user_id, 'postedAt': posted_at},
            {'postId': pid4, 'postedByUserId': pb_user_id, 'postedAt': posted_at},
        ]
    )
    feed_dynamo.add_posts_to_feed(user_id, posts_generator)
    feed = list(feed_dynamo.generate_feed(user_id))
    assert sorted([f['partitionKey'] for f in feed]) == sorted(
        [f'post/{pid1}', f'post/{pid2}', f'post/{pid3}', f'post/{pid4}']
    )
    items = list(feed_dynamo.generate_items(user_id))
    assert sorted([i['postId'] for i in items]) == sorted([pid1, pid2, pid3, pid4])

    # delete three posts, verify
    feed_dynamo.delete_by_post_owner(user_id, pb_user_id)
    feed = list(feed_dynamo.generate_feed(user_id))
    assert [f['partitionKey'] for f in feed] == [f'post/{pid2}']
    items = list(feed_dynamo.generate_items(user_id))
    assert [i['postId'] for i in items] == [pid2]

    # delete last post, verify
    feed_dynamo.delete_by_post_owner(user_id, opb_user_id)
    assert list(feed_dynamo.generate_feed(user_id)) == []
    assert list(feed_dynamo.generate_items(user_id)) == []


def test_add_post_to_feeds(feed_dynamo):
    feed_uids = [str(uuid4()), str(uuid4())]

    # check nothing in feeds
    assert list(feed_dynamo.generate_feed(feed_uids[0])) == []
    assert list(feed_dynamo.generate_feed(feed_uids[1])) == []
    assert list(feed_dynamo.generate_items(feed_uids[0])) == []
    assert list(feed_dynamo.generate_items(feed_uids[1])) == []

    # add post to no feeds - verify no error
    post_id = str(uuid4())
    posted_at = pendulum.now('utc').to_iso8601_string()
    post_item = {
        'postId': post_id,
        'postedByUserId': str(uuid4()),
        'postedAt': posted_at,
    }
    assert feed_dynamo.add_post_to_feeds(iter([]), post_item) == []

    # add post to the feeds
    assert feed_dynamo.add_post_to_feeds(iter(feed_uids), post_item) == feed_uids

    # check the feeds are as expected
    assert [f['partitionKey'] for f in feed_dynamo.generate_feed(feed_uids[0])] == [f'post/{post_id}']
    assert [f['partitionKey'] for f in feed_dynamo.generate_feed(feed_uids[1])] == [f'post/{post_id}']
    assert [i['postId'] for i in feed_dynamo.generate_items(feed_uids[0])] == [post_id]
    assert [i['postId'] for i in feed_dynamo.generate_items(feed_uids[1])] == [post_id]

    # add another post to the feeds
    posted_at = pendulum.now('utc').to_iso8601_string()
    post_id_2 = str(uuid4())
    post_item = {
        'postId': post_id_2,
        'postedByUserId': str(uuid4()),
        'postedAt': posted_at,
    }
    assert feed_dynamo.add_post_to_feeds(iter(feed_uids), post_item) == feed_uids

    # check the feeds are as expected
    assert sorted([f['partitionKey'] for f in feed_dynamo.generate_feed(feed_uids[0])]) == sorted(
        [f'post/{post_id}', f'post/{post_id_2}']
    )
    assert sorted([f['partitionKey'] for f in feed_dynamo.generate_feed(feed_uids[1])]) == sorted(
        [f'post/{post_id}', f'post/{post_id_2}']
    )
    assert sorted([i['postId'] for i in feed_dynamo.generate_items(feed_uids[0])]) == sorted([post_id, post_id_2])
    assert sorted([i['postId'] for i in feed_dynamo.generate_items(feed_uids[1])]) == sorted([post_id, post_id_2])


def test_delete_by_post(feed_dynamo):
    feed_uids = [str(uuid4()), str(uuid4())]

    # delete post from feeds where it doesn't exist - verify no error
    assert feed_dynamo.delete_by_post(str(uuid4())) == []

    # add a post to two feeds
    posted_at = pendulum.now('utc').to_iso8601_string()
    post_id = str(uuid4())
    post_item = {
        'postId': post_id,
        'postedByUserId': str(uuid4()),
        'postedAt': posted_at,
    }
    assert feed_dynamo.add_post_to_feeds(iter(feed_uids), post_item) == feed_uids

    # add another post to one of the feeds
    post_id_2 = str(uuid4())
    post_item = {
        'postId': post_id_2,
        'postedByUserId': str(uuid4()),
        'postedAt': posted_at,
    }
    assert feed_dynamo.add_post_to_feeds(iter(feed_uids[:1]), post_item) == feed_uids[:1]

    # verify the two feeds look as expected
    assert sorted([f['partitionKey'] for f in feed_dynamo.generate_feed(feed_uids[0])]) == sorted(
        [f'post/{post_id}', f'post/{post_id_2}']
    )
    assert [f['partitionKey'] for f in feed_dynamo.generate_feed(feed_uids[1])] == [f'post/{post_id}']
    assert sorted([i['postId'] for i in feed_dynamo.generate_items(feed_uids[0])]) == sorted([post_id, post_id_2])
    assert [i['postId'] for i in feed_dynamo.generate_items(feed_uids[1])] == [post_id]

    # delete a post from the feeds
    assert sorted(feed_dynamo.delete_by_post(post_id)) == sorted(feed_uids)

    # verify the two feeds look as expected
    assert [f['partitionKey'] for f in feed_dynamo.generate_feed(feed_uids[0])] == [f'post/{post_id_2}']
    assert [f['partitionKey'] for f in feed_dynamo.generate_feed(feed_uids[1])] == []
    assert [i['postId'] for i in feed_dynamo.generate_items(feed_uids[0])] == [post_id_2]
    assert [i['postId'] for i in feed_dynamo.generate_items(feed_uids[1])] == []

    # delete the other post from the feeds
    assert feed_dynamo.delete_by_post(post_id_2) == feed_uids[:1]

    # verify the two feeds look as expected
    assert [f['partitionKey'] for f in feed_dynamo.generate_feed(feed_uids[0])] == []
    assert [f['partitionKey'] for f in feed_dynamo.generate_feed(feed_uids[1])] == []
    assert [i['postId'] for i in feed_dynamo.generate_items(feed_uids[0])] == []
    assert [i['postId'] for i in feed_dynamo.generate_items(feed_uids[1])] == []


def test_generate_feed_pks_by_post(feed_dynamo):
    feed_user_id_1 = 'fuid1'
    feed_user_id_2 = 'fuid2'
    posted_at = pendulum.now('utc').to_iso8601_string()
    post_item_1 = {'postId': 'pid1', 'postedByUserId': 'pbuid1', 'postedAt': posted_at}
    post_item_2 = {'postId': 'pid3', 'postedByUserId': 'pbuid2', 'postedAt': posted_at}

    # add two posts to two different feeds
    feed_dynamo.add_posts_to_feed(feed_user_id_1, iter([post_item_1, post_item_2]))
    feed_dynamo.add_posts_to_feed(feed_user_id_2, iter([post_item_1]))

    # verify the feed looks as expected
    assert sorted([f['partitionKey'] for f in feed_dynamo.generate_feed(feed_user_id_1)]) == [
        'post/pid1',
        'post/pid3',
    ]
    assert sorted([f['partitionKey'] for f in feed_dynamo.generate_feed(feed_user_id_2)]) == ['post/pid1']

    # verify we can generate items in the feed by post
    assert set(tuple(item.items()) for item in feed_dynamo.generate_feed_pks_by_post('pid1')) == {
        (('partitionKey', 'post/pid1'), ('sortKey', 'feed/fuid1')),
        (('partitionKey', 'post/pid1'), ('sortKey', 'feed/fuid2')),
    }
    assert list(feed_dynamo.generate_feed_pks_by_post('pid2')) == []
    assert list(feed_dynamo.generate_feed_pks_by_post('pid3')) == [
        {'partitionKey': 'post/pid3', 'sortKey': 'feed/fuid1'},
    ]


def test_generate_keys_by_post(feed_dynamo):
    feed_user_id_1, feed_user_id_2 = str(uuid4()), str(uuid4())
    post_id_1, post_id_2 = str(uuid4()), str(uuid4())
    posted_at = pendulum.now('utc').to_iso8601_string()
    post_item_1 = {'postId': post_id_1, 'postedByUserId': 'pbuid1', 'postedAt': posted_at}
    post_item_2 = {'postId': post_id_2, 'postedByUserId': 'pbuid2', 'postedAt': posted_at}

    # add two posts to two different feeds
    feed_dynamo.add_posts_to_feed(feed_user_id_1, iter([post_item_1, post_item_2]))
    feed_dynamo.add_posts_to_feed(feed_user_id_2, iter([post_item_1]))

    # verify the feed looks as expected
    assert sorted([i['postId'] for i in feed_dynamo.generate_items(feed_user_id_1)]) == sorted(
        [post_id_1, post_id_2]
    )
    assert sorted([i['postId'] for i in feed_dynamo.generate_items(feed_user_id_2)]) == [post_id_1]

    # verify we can generate items in the feed by post
    assert set(tuple(key.items()) for key in feed_dynamo.generate_keys_by_post(post_id_1)) == {
        (('postId', post_id_1), ('feedUserId', feed_user_id_1)),
        (('postId', post_id_1), ('feedUserId', feed_user_id_2)),
    }
    assert list(feed_dynamo.generate_keys_by_post(post_id_2)) == [
        {'postId': post_id_2, 'feedUserId': feed_user_id_1},
    ]
    assert list(feed_dynamo.generate_keys_by_post(str(uuid4()))) == []


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
    assert sorted([f['partitionKey'] for f in feed_dynamo.generate_feed(feed_user_id)]) == [
        'post/pid1',
        'post/pid2',
        'post/pid3',
    ]

    # verify we can generate items in the feed by who posted them
    feed_pk_gen = feed_dynamo.generate_feed_pks_by_posted_by_user(feed_user_id, pb_user_id_1)
    assert sorted([feed_dynamo.parse_pk(fpk)[0] for fpk in feed_pk_gen]) == ['pid1', 'pid3']

    feed_pk_gen = feed_dynamo.generate_feed_pks_by_posted_by_user(feed_user_id, pb_user_id_2)
    assert [feed_dynamo.parse_pk(fpk)[0] for fpk in feed_pk_gen] == ['pid2']

    # check we correctly handle a user that has posted no posts to the feed
    assert list(feed_dynamo.generate_feed_pks_by_posted_by_user(feed_user_id, 'other-uid')) == []


def test_generate_keys_by_posted_by_user(feed_dynamo):
    feed_user_id = str(uuid4())
    pb_user_id_1, pb_user_id_2 = str(uuid4()), str(uuid4())

    # add three posts by different users to the feed
    posted_at = pendulum.now('utc').to_iso8601_string()
    pid1, pid2, pid3 = str(uuid4()), str(uuid4()), str(uuid4())
    post_items = [
        {'postId': pid1, 'postedByUserId': pb_user_id_1, 'postedAt': posted_at},
        {'postId': pid2, 'postedByUserId': pb_user_id_2, 'postedAt': posted_at},
        {'postId': pid3, 'postedByUserId': pb_user_id_1, 'postedAt': posted_at},
    ]
    feed_dynamo.add_posts_to_feed(feed_user_id, iter(post_items))

    # verify the feed looks as expected
    assert sorted([i['postId'] for i in feed_dynamo.generate_items(feed_user_id)]) == sorted([pid1, pid2, pid3])

    # verify we can generate items in the feed by who posted them
    key_generator = feed_dynamo.generate_keys_by_posted_by_user(feed_user_id, pb_user_id_1)
    assert sorted(tuple(key.items()) for key in key_generator) == sorted(
        [(('postId', pid1), ('feedUserId', feed_user_id)), (('postId', pid3), ('feedUserId', feed_user_id))]
    )
    assert list(feed_dynamo.generate_keys_by_posted_by_user(feed_user_id, pb_user_id_2)) == [
        {'postId': pid2, 'feedUserId': feed_user_id}
    ]
    assert list(feed_dynamo.generate_keys_by_posted_by_user(feed_user_id, str(uuid4()))) == []
