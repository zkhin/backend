from unittest.mock import call, Mock

from isodate.duration import Duration
import pytest

from app.models.feed import FeedManager
from app.models.followed_first_story import FollowedFirstStoryManager
from app.models.post.enums import PostStatus
from app.models.post.exceptions import PostException


@pytest.fixture
def user(user_manager):
    yield user_manager.create_cognito_only_user('pbuid', 'pbUname')


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user.id, 'pid1', text='t')


@pytest.fixture
def post_with_media(post_manager, user_manager):
    user = user_manager.create_cognito_only_user('pbuid2', 'pbUname2')
    yield post_manager.add_post(user.id, 'pid2', media_uploads=[{'mediaId': 'mid', 'mediaType': 'IMAGE'}], text='t')


@pytest.fixture
def post_with_media_with_expiration(post_manager, user_manager):
    user = user_manager.create_cognito_only_user('pbuid2', 'pbUname2')
    yield post_manager.add_post(
        user.id, 'pid2', media_uploads=[{'mediaId': 'mid', 'mediaType': 'IMAGE'}], text='t',
        lifetime_duration=Duration(hours=1),
    )


@pytest.fixture
def post_with_media_with_album(album_manager, post_manager, user_manager):
    user = user_manager.create_cognito_only_user('pbuid2', 'pbUname2')
    album = album_manager.add_album(user.id, 'aid-2', 'album name')
    yield post_manager.add_post(
        user.id, 'pid2', media_uploads=[{'mediaId': 'mid', 'mediaType': 'IMAGE'}], text='t', album_id=album.id
    )


def test_complete_error_for_status(post_manager, post):
    # sneak behind the model change the post's status
    transacts = [post_manager.dynamo.transact_set_post_status(post.item, PostStatus.COMPLETED)]
    post_manager.dynamo.client.transact_write_items(transacts)
    post.refresh_item()

    with pytest.raises(PostException) as error_info:
        post.complete()
    assert PostStatus.COMPLETED in str(error_info.value)

    # sneak behind the model change the post's status
    transacts = [post_manager.dynamo.transact_set_post_status(post.item, PostStatus.ARCHIVED)]
    post_manager.dynamo.client.transact_write_items(transacts)
    post.refresh_item()

    with pytest.raises(PostException) as error_info:
        post.complete()
    assert PostStatus.ARCHIVED in str(error_info.value)

    # sneak behind the model change the post's status
    transacts = [post_manager.dynamo.transact_set_post_status(post.item, PostStatus.DELETING)]
    post_manager.dynamo.client.transact_write_items(transacts)
    post.refresh_item()

    with pytest.raises(PostException) as error_info:
        post.complete()
    assert PostStatus.DELETING in str(error_info.value)


def test_complete(post_manager, post_with_media, user_manager):
    post = post_with_media
    posted_by_user_id = post.item['postedByUserId']
    posted_by_user = user_manager.get_user(posted_by_user_id)

    # mock out some calls to far-flung other managers
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.feed_manager = Mock(FeedManager({}))

    # check starting state
    assert posted_by_user.item.get('postCount', 0) == 0
    assert post.item['postStatus'] == PostStatus.PENDING

    # complete the post, check state
    post.complete()
    assert post.item['postStatus'] == PostStatus.COMPLETED
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 1

    # check correct calls happened to far-flung other managers
    assert post.followed_first_story_manager.mock_calls == []
    assert post.feed_manager.mock_calls == [
        call.add_post_to_followers_feeds(posted_by_user_id, post.item),
    ]


def test_complete_with_expiration(post_manager, post_with_media_with_expiration, user_manager):
    post = post_with_media_with_expiration
    posted_by_user_id = post.item['postedByUserId']
    posted_by_user = user_manager.get_user(posted_by_user_id)

    # mock out some calls to far-flung other managers
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.feed_manager = Mock(FeedManager({}))

    # check starting state
    assert posted_by_user.item.get('postCount', 0) == 0
    assert post.item['postStatus'] == PostStatus.PENDING

    # complete the post, check state
    post.complete()
    assert post.item['postStatus'] == PostStatus.COMPLETED
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 1

    # check correct calls happened to far-flung other managers
    assert post.followed_first_story_manager.mock_calls == [
        call.refresh_after_story_change(story_now=post.item)
    ]
    assert post.feed_manager.mock_calls == [
        call.add_post_to_followers_feeds(posted_by_user_id, post.item),
    ]


def test_complete_with_album(album_manager, post_manager, post_with_media_with_album, user_manager):
    post = post_with_media_with_album
    posted_by_user_id = post.item['postedByUserId']
    posted_by_user = user_manager.get_user(posted_by_user_id)
    album = album_manager.get_album(post.item['albumId'])

    # mock out some calls to far-flung other managers
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.feed_manager = Mock(FeedManager({}))

    # check starting state
    assert album.item.get('postCount', 0) == 0
    assert posted_by_user.item.get('postCount', 0) == 0
    assert post.item['postStatus'] == PostStatus.PENDING

    # complete the post, check state
    post.complete()
    assert post.item['postStatus'] == PostStatus.COMPLETED
    album.refresh_item()
    assert album.item.get('postCount', 0) == 1
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 1

    # check correct calls happened to far-flung other managers
    assert post.followed_first_story_manager.mock_calls == []
    assert post.feed_manager.mock_calls == [
        call.add_post_to_followers_feeds(posted_by_user_id, post.item),
    ]
