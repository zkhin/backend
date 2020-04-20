from unittest.mock import call, Mock
import uuid

import pendulum
import pytest

from app.models.feed import FeedManager
from app.models.followed_first_story import FollowedFirstStoryManager
from app.models.post.enums import PostStatus, PostType
from app.models.post.exceptions import PostException
from app.utils import image_size


@pytest.fixture
def user(user_manager, cognito_client):
    user_id = str(uuid.uuid4())
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username=user_id)
    yield user_manager.create_cognito_only_user(user_id, str(uuid.uuid4())[:8])


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user.id, 'pid1', PostType.TEXT_ONLY, text='t')


@pytest.fixture
def post_with_media(post_manager, user):
    post = post_manager.add_post(user.id, 'pid1', PostType.IMAGE, text='t')
    post.dynamo.set_checksum(post.id, post.item['postedAt'], 'checksum1')
    yield post


@pytest.fixture
def post_set_as_user_photo(post_manager, user):
    post = post_manager.add_post(user.id, 'pid2', PostType.IMAGE, set_as_user_photo=True)
    post.dynamo.set_checksum(post.id, post.item['postedAt'], 'checksum2')
    post.dynamo.set_is_verified(post.id, True)
    yield post


@pytest.fixture
def post_with_media_with_expiration(post_manager, user):
    post = post_manager.add_post(
        user.id, 'pid2', PostType.IMAGE, text='t', lifetime_duration=pendulum.duration(hours=1),
    )
    post.dynamo.set_checksum(post.id, post.item['postedAt'], 'checksum2')
    yield post


@pytest.fixture
def post_with_media_with_album(album_manager, post_manager, user):
    album = album_manager.add_album(user.id, 'aid-3', 'album name 3')
    post = post_manager.add_post(user.id, 'pid3', PostType.IMAGE, text='t', album_id=album.id)
    post.dynamo.set_checksum(post.id, post.item['postedAt'], 'checksum3')
    yield post


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


def test_complete(post_manager, post_with_media, user_manager, appsync_client):
    post = post_with_media
    posted_by_user_id = post.item['postedByUserId']
    posted_by_user = user_manager.get_user(posted_by_user_id)

    # mock out some calls to far-flung other managers
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.feed_manager = Mock(FeedManager({}))

    # check starting state
    assert posted_by_user.item.get('postCount', 0) == 0
    assert post.item['postStatus'] == PostStatus.PENDING
    assert appsync_client.mock_calls == []

    # complete the post, check state
    post.complete()
    assert post.item['postStatus'] == PostStatus.COMPLETED
    assert 'originalPostId' not in post.item
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 1

    # check correct calls happened to far-flung other managers
    assert post.followed_first_story_manager.mock_calls == []
    assert post.feed_manager.mock_calls == [
        call.add_post_to_followers_feeds(posted_by_user_id, post.item),
    ]

    # check the subscription was triggered
    assert len(appsync_client.mock_calls) == 1
    assert 'triggerPostNotification' in appsync_client.send.call_args.args[0]
    assert appsync_client.send.call_args.args[1]['input']['postId'] == post.id


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


def test_complete_with_album(album_manager, post_manager, post_with_media_with_album, user_manager, image_data):
    post = post_with_media_with_album
    posted_by_user_id = post.item['postedByUserId']
    posted_by_user = user_manager.get_user(posted_by_user_id)
    album = album_manager.get_album(post.item['albumId'])
    assert post.item['gsiK3PartitionKey'] == f'post/{album.id}'
    assert post.item['gsiK3SortKey'] == -1

    # put media out in mocked s3 for the post, so album art can be generated
    path = post.media.get_s3_path(image_size.NATIVE)
    post_manager.clients['s3_uploads'].put_object(path, image_data, 'application/octet-stream')
    post.media.process_upload()

    # mock out some calls to far-flung other managers
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.feed_manager = Mock(FeedManager({}))

    # check starting state
    assert album.item.get('postCount', 0) == 0
    assert album.item.get('rankCount', 0) == 0
    assert posted_by_user.item.get('postCount', 0) == 0
    assert post.item['postStatus'] == PostStatus.PENDING

    # complete the post, check state
    post.complete()
    assert post.item['postStatus'] == PostStatus.COMPLETED
    assert post.item['gsiK3PartitionKey'] == f'post/{album.id}'
    assert post.item['gsiK3SortKey'] == 0
    album.refresh_item()
    assert album.item.get('postCount', 0) == 1
    assert album.item.get('rankCount', 0) == 1
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 1

    # check correct calls happened to far-flung other managers
    assert post.followed_first_story_manager.mock_calls == []
    assert post.feed_manager.mock_calls == [
        call.add_post_to_followers_feeds(posted_by_user_id, post.item),
    ]


def test_complete_with_original_post(post_manager, post_with_media, post_with_media_with_expiration):
    post1, post2 = post_with_media, post_with_media_with_expiration

    # put some native-size media up in the mock s3, same content
    path1 = post1.get_image_path(image_size.NATIVE)
    path2 = post2.get_image_path(image_size.NATIVE)
    post1.s3_uploads_client.put_object(path1, b'anything', 'application/octet-stream')
    post2.s3_uploads_client.put_object(path2, b'anything', 'application/octet-stream')

    # mock out some calls to far-flung other managers
    post1.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post1.feed_manager = Mock(FeedManager({}))
    post2.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post2.feed_manager = Mock(FeedManager({}))

    # complete the post that has the earlier postedAt, should not get an originalPostId
    post1.set_checksum()
    post1.complete()
    assert post1.item['postStatus'] == PostStatus.COMPLETED
    assert 'originalPostId' not in post1.item
    post1.refresh_item()
    assert post1.item['postStatus'] == PostStatus.COMPLETED
    assert 'originalPostId' not in post1.item

    # complete the post with the later postedAt, *should* get an originalPostId
    post2.set_checksum()
    post2.complete()
    assert post2.item['postStatus'] == PostStatus.COMPLETED
    assert post2.item['originalPostId'] == post1.id
    post2.refresh_item()
    assert post2.item['postStatus'] == PostStatus.COMPLETED
    assert post2.item['originalPostId'] == post1.id


def test_complete_with_set_as_user_photo(post_manager, user, post_with_media, post_set_as_user_photo):
    # complete the post without use_as_user_photo, verify user photo change api no called
    post_with_media.user.update_photo = Mock()
    post_with_media.complete()
    assert post_with_media.user.update_photo.mock_calls == []

    # complete the post without use_as_user_photo, verify user photo change api called
    post_set_as_user_photo.user.update_photo = Mock()
    post_set_as_user_photo.complete()
    assert post_set_as_user_photo.user.update_photo.mock_calls == [call(post_set_as_user_photo.id)]
