from uuid import uuid4

import pendulum
import pytest

from app.models.post.enums import PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


def test_add_users_posts_to_feed(feed_manager, post_manager, user, cognito_client):
    feed_user_id = 'fuid'

    # user has two posts
    post_id_1 = 'pid1'
    post_id_2 = 'pid2'
    post_manager.add_post(user, post_id_1, PostType.TEXT_ONLY, text='t')
    post_manager.add_post(user, post_id_2, PostType.TEXT_ONLY, text='t')

    # verify no posts in feed
    assert list(feed_manager.dynamo.generate_feed(feed_user_id)) == []

    # add pb's user's posts to the feed
    feed_manager.add_users_posts_to_feed(feed_user_id, user.id)

    # verify those posts made it to the feed
    assert sorted([f['partitionKey'] for f in feed_manager.dynamo.generate_feed(feed_user_id)]) == [
        'post/' + post_id_1,
        'post/' + post_id_2,
    ]


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
    assert feed_manager.add_post_to_followers_feeds(our_user.id, post_item) == ['ouid']

    # check feeds
    assert [f['partitionKey'] for f in feed_manager.dynamo.generate_feed(our_user.id)] == ['post/pid1']
    assert list(feed_manager.dynamo.generate_feed(their_user.id)) == []
    assert list(feed_manager.dynamo.generate_feed(another_user.id)) == []

    # they follow us
    feed_manager.follower_manager.dynamo.add_following(their_user.id, our_user.id, 'FOLLOWING')

    # add a post to all our followers and us
    posted_at = pendulum.now('utc').to_iso8601_string()
    post_item = {
        'postId': 'pid2',
        'postedByUserId': our_user.id,
        'postedAt': posted_at,
    }
    assert feed_manager.add_post_to_followers_feeds(our_user.id, post_item) == ['ouid', 'tuid']

    # check feeds
    assert sorted([f['partitionKey'] for f in feed_manager.dynamo.generate_feed(our_user.id)]) == [
        'post/pid1',
        'post/pid2',
    ]
    assert [f['partitionKey'] for f in feed_manager.dynamo.generate_feed(their_user.id)] == ['post/pid2']
    assert list(feed_manager.dynamo.generate_feed(another_user.id)) == []
