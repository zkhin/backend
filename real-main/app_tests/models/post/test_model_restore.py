import decimal
import uuid
from unittest import mock

import pendulum
import pytest

from app.models.post.enums import PostStatus, PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def post_with_expiration(post_manager, user):
    yield post_manager.add_post(
        user, 'pid2', PostType.TEXT_ONLY, text='t', lifetime_duration=pendulum.duration(hours=1),
    )


@pytest.fixture
def post_with_media(post_manager, user):
    yield post_manager.add_post(user, 'pid2', PostType.IMAGE, text='t')


@pytest.fixture
def post_with_media_completed(post_manager, user, image_data_b64):
    yield post_manager.add_post(user, 'pid2', PostType.IMAGE, image_input={'imageData': image_data_b64}, text='t')


def test_restore_completed_text_only_post_with_expiration(post_manager, post_with_expiration, user_manager):
    post = post_with_expiration

    # archive the post
    post.archive()
    assert post.item['postStatus'] == PostStatus.ARCHIVED

    # mock out some calls to far-flung other managers
    post.follower_manager = mock.Mock(post.follower_manager)

    # restore the post
    post.restore()
    assert post.item['postStatus'] == PostStatus.COMPLETED

    # check the post straight from the db
    post.refresh_item()
    assert post.item['postStatus'] == PostStatus.COMPLETED

    # check calls to mocked out managers
    assert post.follower_manager.mock_calls == [
        mock.call.refresh_first_story(story_now=post.item),
    ]


def test_restore_completed_media_post(post_manager, post_with_media_completed, user_manager):
    post = post_with_media_completed

    # archive the post
    post.archive()
    assert post.item['postStatus'] == PostStatus.ARCHIVED

    # mock out some calls to far-flung other managers
    post.follower_manager = mock.Mock(post.follower_manager)

    # restore the post
    post.restore()
    assert post.item['postStatus'] == PostStatus.COMPLETED

    # check the DB again
    post.refresh_item()
    assert post.item['postStatus'] == PostStatus.COMPLETED

    # check calls to mocked out managers
    assert post.follower_manager.mock_calls == []


def test_restore_completed_post_in_album(album_manager, post_manager, post_with_media_completed, user_manager):
    post = post_with_media_completed
    album = album_manager.add_album(post.user_id, 'aid', 'album name')
    post.set_album(album.id)

    # archive the post
    post.archive()
    assert post.item['postStatus'] == PostStatus.ARCHIVED
    assert post.item['gsiK3PartitionKey'] == f'post/{album.id}'
    assert post.item['gsiK3SortKey'] == -1

    # check our starting post count
    album.refresh_item()
    assert album.item.get('postCount', 0) == 0
    assert album.item.get('rankCount', 0) == 1

    # mock out some calls to far-flung other managers
    post.follower_manager = mock.Mock(post.follower_manager)

    # restore the post
    post.restore()
    assert post.item['postStatus'] == PostStatus.COMPLETED
    assert post.item['albumId'] == album.id
    assert post.item['gsiK3PartitionKey'] == f'post/{album.id}'
    assert post.item['gsiK3SortKey'] == pytest.approx(decimal.Decimal(1 / 3))

    # check the post straight from the db
    post.refresh_item()
    assert post.item['postStatus'] == PostStatus.COMPLETED
    assert post.item['albumId'] == album.id
    assert post.item['gsiK3PartitionKey'] == f'post/{album.id}'
    assert post.item['gsiK3SortKey'] == pytest.approx(decimal.Decimal(1 / 3))

    # check our post count - should have incremented
    album.refresh_item()
    assert album.item.get('postCount', 0) == 1
    assert album.item.get('rankCount', 0) == 2

    # check calls to mocked out managers
    assert post.follower_manager.mock_calls == []
