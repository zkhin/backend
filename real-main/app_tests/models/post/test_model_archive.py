from unittest.mock import call, Mock

import pendulum
import pytest

from app.models.feed import FeedManager
from app.models.followed_first_story import FollowedFirstStoryManager
from app.models.like import LikeManager
from app.models.media.enums import MediaStatus
from app.models.post.enums import PostStatus


@pytest.fixture
def user(user_manager):
    yield user_manager.create_cognito_only_user('pbuid', 'pbUname')


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user.id, 'pid1', text='t')


@pytest.fixture
def post_with_expiration(post_manager, user_manager):
    user = user_manager.create_cognito_only_user('pbuid2', 'pbUname2')
    yield post_manager.add_post(user.id, 'pid2', text='t', lifetime_duration=pendulum.duration(hours=1))


@pytest.fixture
def post_with_album(album_manager, post_manager, user_manager):
    user = user_manager.create_cognito_only_user('pbuid2', 'pbUname2')
    album = album_manager.add_album(user.id, 'aid', 'album name')
    yield post_manager.add_post(user.id, 'pid2', text='t', album_id=album.id)


@pytest.fixture
def post_with_media(post_manager, user_manager):
    user = user_manager.create_cognito_only_user('pbuid2', 'pbUname2')
    yield post_manager.add_post(user.id, 'pid2', media_uploads=[{'mediaId': 'mid', 'mediaType': 'IMAGE'}], text='t')


def test_archive_post_wrong_status(post_manager, post):
    # change the post to DELETING status
    transacts = [post_manager.dynamo.transact_set_post_status(post.item, PostStatus.DELETING)]
    post_manager.dynamo.client.transact_write_items(transacts)
    post.refresh_item()

    # verify we can't archive a post if we're in the process of deleting it
    with pytest.raises(post_manager.exceptions.PostException):
        post.archive()


def test_archive_pending_post(post_manager, post_with_media, user_manager):
    post = post_with_media
    posted_by_user_id = post.item['postedByUserId']
    posted_by_user = user_manager.get_user(posted_by_user_id)

    # check our starting post count
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 0

    # mock out some calls to far-flung other managers
    post.like_manager = Mock(LikeManager({}))
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.feed_manager = Mock(FeedManager({}))

    # archive the post, check it got to media
    post.archive()
    assert post.item['postStatus'] == PostStatus.ARCHIVED
    assert len(post.item['mediaObjects']) == 1
    assert post.item['mediaObjects'][0]['mediaStatus'] == MediaStatus.ARCHIVED

    # check the post count was not changed
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 0

    # check calls to mocked out managers
    assert post.like_manager.mock_calls == [
        call.dislike_all_of_post(post.id),
    ]
    assert post.followed_first_story_manager.mock_calls == []
    assert post.feed_manager.mock_calls == []


def test_archive_expired_completed_post(post_manager, post_with_expiration, user_manager):
    post = post_with_expiration
    posted_by_user_id = post.item['postedByUserId']
    posted_by_user = user_manager.get_user(posted_by_user_id)

    # check our starting post count
    posted_by_user.refresh_item()
    assert posted_by_user.item['postCount'] == 1

    # mock out some calls to far-flung other managers
    post.like_manager = Mock(LikeManager({}))
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.feed_manager = Mock(FeedManager({}))

    # archive the post
    post.archive()
    assert post.item['postStatus'] == PostStatus.ARCHIVED
    assert len(post.item['mediaObjects']) == 0

    # check the post count decremented
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 0

    # check calls to mocked out managers
    assert post.like_manager.mock_calls == [
        call.dislike_all_of_post(post.id),
    ]
    assert post.followed_first_story_manager.mock_calls == [
        call.refresh_after_story_change(story_prev=post.item),
    ]
    assert post.feed_manager.mock_calls == [
        call.delete_post_from_followers_feeds(posted_by_user_id, post.id),
    ]


def test_archive_completed_post_with_album(album_manager, post_manager, post_with_album, user_manager):
    post = post_with_album
    posted_by_user_id = post.item['postedByUserId']
    album = album_manager.get_album(post.item['albumId'])
    posted_by_user = user_manager.get_user(posted_by_user_id)

    # check our starting post count
    album.refresh_item()
    assert album.item['postCount'] == 1
    posted_by_user.refresh_item()
    assert posted_by_user.item['postCount'] == 1

    # mock out some calls to far-flung other managers
    post.like_manager = Mock(LikeManager({}))
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.feed_manager = Mock(FeedManager({}))

    # archive the post
    post.archive()
    assert post.item['postStatus'] == PostStatus.ARCHIVED
    assert len(post.item['mediaObjects']) == 0

    # check the post is still in the album, but since it's no longer completed, it doesn't show in the count
    assert post.item['albumId'] == album.id
    album.refresh_item()
    assert album.item.get('postCount', 0) == 0

    # check the user post count decremented
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 0

    # check calls to mocked out managers
    assert post.like_manager.mock_calls == [
        call.dislike_all_of_post(post.id),
    ]
    assert post.followed_first_story_manager.mock_calls == []
    assert post.feed_manager.mock_calls == [
        call.delete_post_from_followers_feeds(posted_by_user_id, post.id),
    ]
