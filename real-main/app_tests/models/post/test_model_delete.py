from unittest.mock import call, Mock

import pendulum
import pytest

from app.models.comment import CommentManager
from app.models.feed import FeedManager
from app.models.flag import FlagManager
from app.models.followed_first_story import FollowedFirstStoryManager
from app.models.like import LikeManager
from app.models.media.enums import MediaStatus, MediaSize
from app.models.post.enums import PostStatus
from app.models.post_view import PostViewManager
from app.models.trending import TrendingManager


@pytest.fixture
def post_with_expiration(post_manager, user_manager):
    user = user_manager.create_cognito_only_user('pbuid2', 'pbUname2')
    yield post_manager.add_post(user.id, 'pid2', text='t', lifetime_duration=pendulum.duration(hours=1))


@pytest.fixture
def post_with_album(album_manager, post_manager, user_manager, image_data_b64, mock_post_verification_api):
    user = user_manager.create_cognito_only_user('pbuid2', 'pbUname2')
    album = album_manager.add_album(user.id, 'aid', 'album name')
    yield post_manager.add_post(
        user.id, 'pid2', media_uploads=[{'mediaId': 'mid2', 'imageData': image_data_b64}], album_id=album.id,
    )


@pytest.fixture
def completed_post_with_media(post_manager, user_manager, image_data_b64, mock_post_verification_api):
    user = user_manager.create_cognito_only_user('pbuid2', 'pbUname2')
    yield post_manager.add_post(
        user.id, 'pid3', media_uploads=[{'mediaId': 'mid3', 'imageData': image_data_b64}],
    )


@pytest.fixture
def post_with_media(post_manager, user_manager):
    user = user_manager.create_cognito_only_user('pbuid2', 'pbUname2')
    yield post_manager.add_post(user.id, 'pid4', media_uploads=[{'mediaId': 'mid'}], text='t')


def test_delete_completed_text_only_post_with_expiration(post_manager, post_with_expiration, user_manager):
    post = post_with_expiration
    posted_by_user_id = post.item['postedByUserId']
    posted_by_user = user_manager.get_user(posted_by_user_id)

    # check our starting post count
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 1

    # mock out some calls to far-flung other managers
    post.comment_manager = Mock(CommentManager({}))
    post.feed_manager = Mock(FeedManager({}))
    post.flag_manager = Mock(FlagManager({}))
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.like_manager = Mock(LikeManager({}))
    post.post_view_manager = Mock(PostViewManager({}))
    post.trending_manager = Mock(TrendingManager({'dynamo': {}}))

    # delete the post
    post.delete()
    assert post.item['postStatus'] == PostStatus.DELETING
    assert post.item['mediaObjects'] == []
    post_item = post.item

    # check the post is no longer in the DB
    post.refresh_item()
    assert post.item is None

    # check our post count - should have decremented
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 0

    # check calls to mocked out managers
    assert post.comment_manager.mock_calls == [
        call.delete_all_on_post(post.id),
    ]
    assert post.flag_manager.mock_calls == [
        call.unflag_all_on_post(post.id),
    ]
    assert post.feed_manager.mock_calls == [
        call.delete_post_from_followers_feeds(posted_by_user_id, post.id),
    ]
    assert post.followed_first_story_manager.mock_calls == [
        call.refresh_after_story_change(story_prev=post_item),
    ]
    assert post.like_manager.mock_calls == [
        call.dislike_all_of_post(post.id),
    ]
    assert post.post_view_manager.mock_calls == [
        call.delete_all_for_post(post.id),
    ]
    assert post.trending_manager.mock_calls == [
        call.dynamo.delete_trending(post.id),
    ]


def test_delete_pending_media_post(post_manager, post_with_media, user_manager):
    post = post_with_media
    media = post_manager.media_manager.init_media(post_with_media.item['mediaObjects'][0])
    posted_by_user_id = post.item['postedByUserId']
    posted_by_user = user_manager.get_user(posted_by_user_id)

    # check our starting post count
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 0

    # mock out some calls to far-flung other managers
    post.comment_manager = Mock(CommentManager({}))
    post.like_manager = Mock(LikeManager({}))
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.feed_manager = Mock(FeedManager({}))
    post.post_view_manager = Mock(PostViewManager({}))
    post.trending_manager = Mock(TrendingManager({'dynamo': {}}))

    # delete the post
    post.delete()
    assert post.item['postStatus'] == PostStatus.DELETING
    assert len(post.item['mediaObjects']) == 1
    assert post.item['mediaObjects'][0]['mediaStatus'] == MediaStatus.DELETING

    # check the db again
    post.refresh_item()
    assert post.item is None
    media.refresh_item()
    assert media.item is None

    # check our post count - should not have changed
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 0

    # check calls to mocked out managers
    assert post.comment_manager.mock_calls == [
        call.delete_all_on_post(post.id),
    ]
    assert post.like_manager.mock_calls == [
        call.dislike_all_of_post(post.id),
    ]
    assert post.followed_first_story_manager.mock_calls == []
    assert post.feed_manager.mock_calls == []
    assert post.post_view_manager.mock_calls == [
        call.delete_all_for_post(post.id),
    ]
    assert post.trending_manager.mock_calls == [
        call.dynamo.delete_trending(post.id),
    ]


def test_delete_completed_media_post(post_manager, completed_post_with_media, user_manager):
    post = completed_post_with_media
    media = post_manager.media_manager.init_media(post.item['mediaObjects'][0])
    posted_by_user_id = post.item['postedByUserId']
    posted_by_user = user_manager.get_user(posted_by_user_id)

    # check our starting post count
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 1

    # mock out some calls to far-flung other managers
    post.comment_manager = Mock(CommentManager({}))
    post.like_manager = Mock(LikeManager({}))
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.feed_manager = Mock(FeedManager({}))
    post.post_view_manager = Mock(PostViewManager({}))
    post.trending_manager = Mock(TrendingManager({'dynamo': {}}))

    # delete the post
    post.delete()
    assert post.item['postStatus'] == PostStatus.DELETING
    assert len(post.item['mediaObjects']) == 1
    assert post.item['mediaObjects'][0]['mediaStatus'] == MediaStatus.DELETING

    # check the all the media got deleted
    for size in MediaSize._ALL:
        path = media.get_s3_path(size)
        assert post_manager.clients['s3_uploads'].exists(path) is False

    # check the DB again
    post.refresh_item()
    assert post.item is None
    media.refresh_item()
    assert media.item is None

    # check our post count - should have decremented
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 0

    # check calls to mocked out managers
    assert post.comment_manager.mock_calls == [
        call.delete_all_on_post(post.id),
    ]
    assert post.like_manager.mock_calls == [
        call.dislike_all_of_post(post.id),
    ]
    assert post.followed_first_story_manager.mock_calls == []
    assert post.feed_manager.mock_calls == [
        call.delete_post_from_followers_feeds(posted_by_user_id, post.id),
    ]
    assert post.post_view_manager.mock_calls == [
        call.delete_all_for_post(post.id),
    ]
    assert post.trending_manager.mock_calls == [
        call.dynamo.delete_trending(post.id),
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
    post.comment_manager = Mock(CommentManager({}))
    post.like_manager = Mock(LikeManager({}))
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.feed_manager = Mock(FeedManager({}))
    post.post_view_manager = Mock(PostViewManager({}))
    post.trending_manager = Mock(TrendingManager({'dynamo': {}}))

    # delete the post
    post.delete()
    assert post.item['postStatus'] == PostStatus.DELETING
    assert len(post.item['mediaObjects']) == 1
    assert post.item['mediaObjects'][0]['mediaStatus'] == MediaStatus.DELETING
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
        call.delete_all_on_post(post.id),
    ]
    assert post.like_manager.mock_calls == [
        call.dislike_all_of_post(post.id),
    ]
    assert post.followed_first_story_manager.mock_calls == []
    assert post.feed_manager.mock_calls == [
        call.delete_post_from_followers_feeds(posted_by_user_id, post.id),
    ]
    assert post.post_view_manager.mock_calls == [
        call.delete_all_for_post(post.id),
    ]
    assert post.trending_manager.mock_calls == [
        call.dynamo.delete_trending(post.id),
    ]
