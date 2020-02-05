import pendulum


def test_add_users_posts_to_feed(feed_manager, post_manager, user_manager):
    posted_by_user = user_manager.create_cognito_only_user('pb-uid', 'pbUname')
    feed_user_id = 'fuid'

    # user has two posts
    post_id_1 = 'pid1'
    post_id_2 = 'pid2'
    post_manager.add_post(posted_by_user.id, post_id_1, text='t')
    post_manager.add_post(posted_by_user.id, post_id_2, text='t')

    # verify no posts in feed
    assert list(feed_manager.dynamo.generate_feed(feed_user_id)) == []

    # add pb's user's posts to the feed
    feed_manager.add_users_posts_to_feed(feed_user_id, posted_by_user.id)

    # verify those posts made it to the feed
    assert sorted([f['postId'] for f in feed_manager.dynamo.generate_feed(feed_user_id)]) == [post_id_1, post_id_2]


def test_delete_users_posts_from_feed(feed_manager):
    posted_by_uid1 = 'pbuid1'
    posted_by_uid2 = 'pbuid2'
    feed_user_id = 'fuid'

    # add two posts by pbuid1 to the feed, and one by pbuid2
    posted_at = pendulum.now('utc').to_iso8601_string()
    posts_generator = iter([{
        'postId': 'pid1',
        'postedByUserId': posted_by_uid1,
        'postedAt': posted_at,
    }, {
        'postId': 'pid2',
        'postedByUserId': posted_by_uid2,
        'postedAt': posted_at,
    }, {
        'postId': 'pid3',
        'postedByUserId': posted_by_uid1,
        'postedAt': posted_at,
    }])
    feed_manager.dynamo.add_posts_to_feed(feed_user_id, posts_generator)

    # verify the feed is as expected
    feed = list(feed_manager.dynamo.generate_feed(feed_user_id))
    assert sorted([f['postId'] for f in feed]) == ['pid1', 'pid2', 'pid3']

    # delete pbuid1's posts
    feed_manager.delete_users_posts_from_feed(feed_user_id, posted_by_uid1)

    # verify the feed is as expected
    feed = list(feed_manager.dynamo.generate_feed(feed_user_id))
    assert [f['postId'] for f in feed] == ['pid2']

    # delete posts from a user that has none
    feed_manager.delete_users_posts_from_feed(feed_user_id, 'p-dne')

    # verify the feed is as expected
    feed = list(feed_manager.dynamo.generate_feed(feed_user_id))
    assert [f['postId'] for f in feed] == ['pid2']

    # delete posts from the other user that posted som
    feed_manager.delete_users_posts_from_feed(feed_user_id, posted_by_uid2)

    # verify the feed is as expected
    assert list(feed_manager.dynamo.generate_feed(feed_user_id)) == []


def test_add_post_to_followers_feeds(feed_manager, user_manager):
    our_user = user_manager.init_user({'userId': 'ouid', 'privacyStatus': 'PUBLIC'})
    their_user = user_manager.init_user({'userId': 'tuid', 'privacyStatus': 'PUBLIC'})
    another_user = user_manager.init_user({'userId': 'auid', 'privacyStatus': 'PUBLIC'})

    # check feeds are empty
    assert list(feed_manager.dynamo.generate_feed(our_user.id)) == []
    assert list(feed_manager.dynamo.generate_feed(their_user.id)) == []
    assert list(feed_manager.dynamo.generate_feed(another_user.id)) == []

    # add a post to all our followers (none) and us
    posted_at = pendulum.now('utc').to_iso8601_string()
    post_item = {
        'postId': 'pid1',
        'postedByUserId': our_user.id,
        'postedAt': posted_at,
    }
    feed_manager.add_post_to_followers_feeds(our_user.id, post_item)

    # check feeds
    assert [f['postId'] for f in feed_manager.dynamo.generate_feed(our_user.id)] == ['pid1']
    assert list(feed_manager.dynamo.generate_feed(their_user.id)) == []
    assert list(feed_manager.dynamo.generate_feed(another_user.id)) == []

    # they follow us
    transacts = [feed_manager.follow_manager.dynamo.transact_add_following(their_user.id, our_user.id, 'FOLLOWING')]
    feed_manager.dynamo.client.transact_write_items(transacts)

    # add a post to all our followers and us
    posted_at = pendulum.now('utc').to_iso8601_string()
    post_item = {
        'postId': 'pid2',
        'postedByUserId': our_user.id,
        'postedAt': posted_at,
    }
    feed_manager.add_post_to_followers_feeds(our_user.id, post_item)

    # check feeds
    assert sorted([f['postId'] for f in feed_manager.dynamo.generate_feed(our_user.id)]) == ['pid1', 'pid2']
    assert [f['postId'] for f in feed_manager.dynamo.generate_feed(their_user.id)] == ['pid2']
    assert list(feed_manager.dynamo.generate_feed(another_user.id)) == []


def test_delete_post_from_followers_feeds(feed_manager, user_manager):
    our_user = user_manager.init_user({'userId': 'ouid', 'privacyStatus': 'PUBLIC'})
    their_user = user_manager.init_user({'userId': 'tuid', 'privacyStatus': 'PUBLIC'})
    another_user = user_manager.init_user({'userId': 'auid', 'privacyStatus': 'PUBLIC'})

    # they follow us
    transacts = [feed_manager.follow_manager.dynamo.transact_add_following(their_user.id, our_user.id, 'FOLLOWING')]
    feed_manager.dynamo.client.transact_write_items(transacts)

    # add a post to all our followers and us
    posted_at = pendulum.now('utc').to_iso8601_string()
    post_item = {
        'postId': 'pid2',
        'postedByUserId': our_user.id,
        'postedAt': posted_at,
    }
    feed_manager.add_post_to_followers_feeds(our_user.id, post_item)

    # add the post to the feed of a user that doesn't follow us
    feed_manager.dynamo.add_posts_to_feed(another_user.id, iter([post_item]))

    # check feeds
    assert [f['postId'] for f in feed_manager.dynamo.generate_feed(our_user.id)] == ['pid2']
    assert [f['postId'] for f in feed_manager.dynamo.generate_feed(their_user.id)] == ['pid2']
    assert [f['postId'] for f in feed_manager.dynamo.generate_feed(another_user.id)] == ['pid2']

    # delete a different post from our feed and our followers
    feed_manager.delete_post_from_followers_feeds(our_user.id, 'pidother')

    # check feeds
    assert [f['postId'] for f in feed_manager.dynamo.generate_feed(our_user.id)] == ['pid2']
    assert [f['postId'] for f in feed_manager.dynamo.generate_feed(their_user.id)] == ['pid2']
    assert [f['postId'] for f in feed_manager.dynamo.generate_feed(another_user.id)] == ['pid2']

    # delete the post of interest from our feed and our followers
    feed_manager.delete_post_from_followers_feeds(our_user.id, 'pid2')

    # check feeds, only deleted from us and our followers
    assert list(feed_manager.dynamo.generate_feed(our_user.id)) == []
    assert list(feed_manager.dynamo.generate_feed(their_user.id)) == []
    assert [f['postId'] for f in feed_manager.dynamo.generate_feed(another_user.id)] == ['pid2']
