from unittest.mock import call, Mock

import pendulum
import pytest

from app.models.feed import FeedManager
from app.models.followed_first_story import FollowedFirstStoryManager
from app.models.media.enums import MediaSize
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
    user = user_manager.create_cognito_only_user('pbuid1', 'pbUname1')
    post = post_manager.add_post(user.id, 'pid1', media_uploads=[{'mediaId': 'mid1', 'mediaType': 'IMAGE'}], text='t')
    post_manager.media_dynamo.set_checksum(post.item['mediaObjects'][0], 'checksum1')
    yield post


@pytest.fixture
def post_with_media_with_expiration(post_manager, user_manager):
    user = user_manager.create_cognito_only_user('pbuid2', 'pbUname2')
    post = post_manager.add_post(
        user.id, 'pid2', media_uploads=[{'mediaId': 'mid2', 'mediaType': 'IMAGE'}], text='t',
        lifetime_duration=pendulum.duration(hours=1),
    )
    post_manager.media_dynamo.set_checksum(post.item['mediaObjects'][0], 'checksum2')
    yield post


@pytest.fixture
def post_with_media_with_album(album_manager, post_manager, user_manager):
    user = user_manager.create_cognito_only_user('pbuid3', 'pbUname3')
    album = album_manager.add_album(user.id, 'aid-3', 'album name 3')
    post = post_manager.add_post(
        user.id, 'pid3', media_uploads=[{'mediaId': 'mid3', 'mediaType': 'IMAGE'}], text='t', album_id=album.id
    )
    post_manager.media_dynamo.set_checksum(post.item['mediaObjects'][0], 'checksum3')
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
    assert 'originalPostId' not in post.item
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


def test_complete_with_original_post(post_manager, post_with_media, post_with_media_with_album):
    post1, post2 = post_with_media, post_with_media_with_album

    # set the checksum on the media of both posts to the same thing
    media1 = post_manager.media_manager.init_media(post1.item['mediaObjects'][0])
    media2 = post_manager.media_manager.init_media(post2.item['mediaObjects'][0])

    # put some native-size media up in the mock s3, same content
    media_path1 = media1.get_s3_path(MediaSize.NATIVE)
    media_path2 = media2.get_s3_path(MediaSize.NATIVE)
    post_manager.clients['s3_uploads'].put_object(media_path1, b'anything', 'application/octet-stream')
    post_manager.clients['s3_uploads'].put_object(media_path2, b'anything', 'application/octet-stream')

    # mock out some calls to far-flung other managers
    post1.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post1.feed_manager = Mock(FeedManager({}))
    post2.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post2.feed_manager = Mock(FeedManager({}))

    # complete the post that has the earlier postedAt, should not get an originalPostId
    media1.set_checksum()
    post1.complete()
    assert post1.item['postStatus'] == PostStatus.COMPLETED
    assert 'originalPostId' not in post1.item
    post1.refresh_item()
    assert post1.item['postStatus'] == PostStatus.COMPLETED
    assert 'originalPostId' not in post1.item

    # complete the post with the later postedAt, *should* get an originalPostId
    media2.set_checksum()
    post2.complete()
    assert post2.item['postStatus'] == PostStatus.COMPLETED
    assert post2.item['originalPostId'] == post1.id
    post2.refresh_item()
    assert post2.item['postStatus'] == PostStatus.COMPLETED
    assert post2.item['originalPostId'] == post1.id
