import uuid
from unittest import mock

import pendulum
import pytest

from app.models import CommentManager, FeedManager, FollowedFirstStoryManager, LikeManager, TrendingManager
from app.models.post.enums import PostStatus, PostType
from app.utils import image_size


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user
user3 = user


@pytest.fixture
def post_with_expiration(post_manager, user):
    yield post_manager.add_post(
        user, 'pid2', PostType.TEXT_ONLY, text='t', lifetime_duration=pendulum.duration(hours=1),
    )


@pytest.fixture
def post_with_album(album_manager, post_manager, user, image_data_b64):
    album = album_manager.add_album(user.id, 'aid', 'album name')
    yield post_manager.add_post(
        user, 'pid2', PostType.IMAGE, image_input={'imageData': image_data_b64}, album_id=album.id,
    )


@pytest.fixture
def completed_post_with_media(post_manager, user, image_data_b64):
    yield post_manager.add_post(user, 'pid3', PostType.IMAGE, image_input={'imageData': image_data_b64})


@pytest.fixture
def post_with_media(post_manager, user):
    yield post_manager.add_post(user, 'pid4', PostType.IMAGE, text='t', image_input={'originalMetadata': '{}'})


def test_delete_completed_text_only_post_with_expiration(post_manager, post_with_expiration, user_manager):
    post = post_with_expiration
    posted_by_user_id = post.item['postedByUserId']
    posted_by_user = user_manager.get_user(posted_by_user_id)

    # check our starting post count
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 1
    assert posted_by_user.item.get('postDeletedCount', 0) == 0

    # mock out some calls to far-flung other managers
    post.comment_manager = mock.Mock(CommentManager({}))
    post.feed_manager = mock.Mock(FeedManager({}))
    post.followed_first_story_manager = mock.Mock(FollowedFirstStoryManager({}))
    post.like_manager = mock.Mock(LikeManager({}))
    post.trending_manager = mock.Mock(TrendingManager({'dynamo': {}}))

    # delete the post
    post.delete()
    assert post.item['postStatus'] == PostStatus.DELETING
    post_item = post.item

    # check the post is no longer in the DB
    post.refresh_item()
    assert post.item is None

    # check our post count - should have decremented
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 0
    assert posted_by_user.item.get('postDeletedCount', 0) == 1

    # check calls to mocked out managers
    assert post.comment_manager.mock_calls == [
        mock.call.delete_all_on_post(post.id),
    ]
    assert post.feed_manager.mock_calls == [
        mock.call.delete_post_from_followers_feeds(posted_by_user_id, post.id),
    ]
    assert post.followed_first_story_manager.mock_calls == [
        mock.call.refresh_after_story_change(story_prev=post_item),
    ]
    assert post.like_manager.mock_calls == [
        mock.call.dislike_all_of_post(post.id),
    ]
    assert post.trending_manager.mock_calls == [
        mock.call.dynamo.delete_trending(post.id),
    ]


def test_delete_pending_media_post(post_manager, post_with_media, user_manager):
    post = post_with_media
    posted_by_user_id = post.item['postedByUserId']
    posted_by_user = user_manager.get_user(posted_by_user_id)
    assert post.image_item
    assert post_manager.dynamo.get_post(post_with_media.id)
    assert post_manager.original_metadata_dynamo.get(post_with_media.id)

    # check our starting post count
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 0

    # mock out some calls to far-flung other managers
    post.comment_manager = mock.Mock(CommentManager({}))
    post.like_manager = mock.Mock(LikeManager({}))
    post.followed_first_story_manager = mock.Mock(FollowedFirstStoryManager({}))
    post.feed_manager = mock.Mock(FeedManager({}))
    post.trending_manager = mock.Mock(TrendingManager({'dynamo': {}}))

    # delete the post
    post.delete()
    assert post.item['postStatus'] == PostStatus.DELETING

    # check the db again
    post.refresh_item()
    post.refresh_image_item()

    assert post.item is None
    assert post.image_item is None
    assert post_manager.original_metadata_dynamo.get(post_with_media.id) is None

    # check our post count - should not have changed
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 0

    # check calls to mocked out managers
    assert post.comment_manager.mock_calls == [
        mock.call.delete_all_on_post(post.id),
    ]
    assert post.like_manager.mock_calls == [
        mock.call.dislike_all_of_post(post.id),
    ]
    assert post.followed_first_story_manager.mock_calls == []
    assert post.feed_manager.mock_calls == []
    assert post.trending_manager.mock_calls == [
        mock.call.dynamo.delete_trending(post.id),
    ]


def test_delete_completed_media_post(post_manager, completed_post_with_media, user_manager):
    post = completed_post_with_media
    posted_by_user_id = post.item['postedByUserId']
    posted_by_user = user_manager.get_user(posted_by_user_id)

    # check our starting post count
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 1

    # mock out some calls to far-flung other managers
    post.comment_manager = mock.Mock(CommentManager({}))
    post.like_manager = mock.Mock(LikeManager({}))
    post.followed_first_story_manager = mock.Mock(FollowedFirstStoryManager({}))
    post.feed_manager = mock.Mock(FeedManager({}))
    post.trending_manager = mock.Mock(TrendingManager({'dynamo': {}}))

    # delete the post
    post.delete()
    assert post.item['postStatus'] == PostStatus.DELETING

    # check the all the images got deleted
    for size in image_size.JPEGS:
        path = post.get_image_path(size)
        assert post_manager.clients['s3_uploads'].exists(path) is False

    # check the DB again
    post.refresh_item()
    post.refresh_image_item()

    assert post.item is None
    assert post.image_item is None

    # check our post count - should have decremented
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 0

    # check calls to mocked out managers
    assert post.comment_manager.mock_calls == [
        mock.call.delete_all_on_post(post.id),
    ]
    assert post.like_manager.mock_calls == [
        mock.call.dislike_all_of_post(post.id),
    ]
    assert post.followed_first_story_manager.mock_calls == []
    assert post.feed_manager.mock_calls == [
        mock.call.delete_post_from_followers_feeds(posted_by_user_id, post.id),
    ]
    assert post.trending_manager.mock_calls == [
        mock.call.dynamo.delete_trending(post.id),
    ]


def test_delete_completed_post_in_album(album_manager, post_manager, post_with_album, user_manager):
    post = post_with_album
    posted_by_user_id = post.item['postedByUserId']
    album = album_manager.get_album(post.item['albumId'])
    posted_by_user = user_manager.get_user(posted_by_user_id)
    assert post.item['gsiK3PartitionKey'] == f'post/{album.id}'
    assert post.item['gsiK3SortKey'] == 0

    # check our starting point
    assert post.item['postStatus'] == PostStatus.COMPLETED
    album.refresh_item()
    assert album.item.get('postCount', 0) == 1
    assert album.item.get('rankCount', 0) == 1
    assert album.item['artHash']
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 1

    # mock out some calls to far-flung other managers
    post.comment_manager = mock.Mock(CommentManager({}))
    post.like_manager = mock.Mock(LikeManager({}))
    post.followed_first_story_manager = mock.Mock(FollowedFirstStoryManager({}))
    post.feed_manager = mock.Mock(FeedManager({}))
    post.trending_manager = mock.Mock(TrendingManager({'dynamo': {}}))

    # delete the post
    post.delete()
    assert post.item['postStatus'] == PostStatus.DELETING
    assert post.item['gsiK3PartitionKey'] == f'post/{album.id}'
    assert post.item['gsiK3SortKey'] == -1

    # check the DB again
    post.refresh_item()
    assert post.item is None

    # check our post count - should have decremented
    album.refresh_item()
    assert album.item.get('postCount', 0) == 0
    assert album.item.get('rankCount', 0) == 1
    assert 'artHash' not in album.item
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 0

    # check calls to mocked out managers
    assert post.comment_manager.mock_calls == [
        mock.call.delete_all_on_post(post.id),
    ]
    assert post.like_manager.mock_calls == [
        mock.call.dislike_all_of_post(post.id),
    ]
    assert post.followed_first_story_manager.mock_calls == []
    assert post.feed_manager.mock_calls == [
        mock.call.delete_post_from_followers_feeds(posted_by_user_id, post.id),
    ]
    assert post.trending_manager.mock_calls == [
        mock.call.dynamo.delete_trending(post.id),
    ]


def test_delete_flags(album_manager, post_manager, completed_post_with_media, user2, user3):
    post = completed_post_with_media

    # flag the post, verify those flags are in the db
    post.flag(user2)
    post.flag(user3)
    assert len(list(post_manager.flag_dynamo.generate_by_item(post.id))) == 2

    # delete the post, verify the flags are also deleted
    post.delete()
    assert len(list(post_manager.flag_dynamo.generate_by_item(post.id))) == 0


def test_delete_views(album_manager, post_manager, completed_post_with_media, user2, user3):
    post = completed_post_with_media

    # view the post, verify those views are in the db
    post.record_view_count(user2.id, 2)
    post.record_view_count(user3.id, 3)
    assert len(list(post_manager.view_dynamo.generate_views(post.id))) == 2

    # delete the post, verify the flags are also deleted
    post.delete()
    assert len(list(post_manager.view_dynamo.generate_views(post.id))) == 0


def test_delete_archived_post(completed_post_with_media):
    post = completed_post_with_media
    post.archive()
    post.user.refresh_item()

    # check starting state
    assert post.status == PostStatus.ARCHIVED
    assert post.user.item.get('postCount', 0) == 0
    assert post.user.item.get('postArchivedCount', 0) == 1
    assert post.user.item.get('postDeletedCount', 0) == 0

    # delete the post
    post.delete()
    post.user.refresh_item()

    # check final state
    assert post.status == PostStatus.DELETING
    assert post.user.item.get('postCount', 0) == 0
    assert post.user.item.get('postArchivedCount', 0) == 0
    assert post.user.item.get('postDeletedCount', 0) == 1
