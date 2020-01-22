from datetime import datetime
import logging
import random
import string
from unittest.mock import call, Mock

from isodate.duration import Duration
import pytest

from app.models.feed import FeedManager
from app.models.followed_first_story import FollowedFirstStoryManager
from app.models.like import LikeManager
from app.models.media.enums import MediaStatus, MediaSize
from app.models.post.enums import PostStatus
from app.models.post.exceptions import PostException
from app.models.post_view import PostViewManager
from app.models.trending import TrendingManager


@pytest.fixture
def user(user_manager):
    yield user_manager.create_cognito_only_user('pbuid', 'pbUname')


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user.id, 'pid1', text='t')


@pytest.fixture
def post_with_expiration(post_manager, user_manager):
    user = user_manager.create_cognito_only_user('pbuid2', 'pbUname2')
    yield post_manager.add_post(user.id, 'pid2', text='t', lifetime_duration=Duration(hours=1))


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


def test_refresh_item(post):
    # go behind their back and edit the post in the DB
    new_post_item = post.dynamo.increment_viewed_by_count(post.id)
    assert new_post_item != post.item

    # now refresh the item, and check they now do match
    post.refresh_item()
    assert new_post_item == post.item


def test_flag(post):
    # verify the flag count
    assert post.item.get('flagCount', 0) == 0

    # flag the post
    post = post.flag('other-user-id')
    assert post.item.get('flagCount', 0) == 1


def test_flag_threshold_met(caplog, post):
    # verify the flag count
    assert post.item.get('flagCount', 0) == 0

    # add enough flags until the threshold is met
    with caplog.at_level(logging.WARNING):
        for _ in range(post.flagged_alert_threshold):
            random_user_id = ''.join(random.choices(string.ascii_lowercase, k=10))
            post.flag(random_user_id)

    # verify an error was logged
    assert 'FLAGGED' in caplog.text
    assert post.id in caplog.text


def test_set_expires_at(post):
    # add a post without an expires at
    assert 'expiresAt' not in post.item

    # set the expires at to something
    now = datetime.utcnow()
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.set_expires_at(now)
    assert post.item['expiresAt'] == now.isoformat() + 'Z'

    # make sure that stuck in db
    post.refresh_item()
    assert post.item['expiresAt'] == now.isoformat() + 'Z'

    # check that the followed_first_story_manager was called correctly
    assert post.followed_first_story_manager.mock_calls == [
        call.refresh_after_story_change(story_prev=None, story_now=post.item),
    ]

    # set the expires at to something else
    post.followed_first_story_manager.reset_mock()
    now = datetime.utcnow()
    post_org_item = post.item.copy()
    post.set_expires_at(now)
    assert post.item['expiresAt'] == now.isoformat() + 'Z'

    # make sure that stuck in db
    post.refresh_item()
    assert post.item['expiresAt'] == now.isoformat() + 'Z'

    # check that the followed_first_story_manager was called correctly
    assert post.followed_first_story_manager.mock_calls == [
        call.refresh_after_story_change(story_prev=post_org_item, story_now=post.item),
    ]


def test_clear_expires_at(post_with_expiration):
    # add a post with an expires at
    post = post_with_expiration
    assert 'expiresAt' in post.item

    # remove the expires at
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post_org_item = post.item.copy()
    post.set_expires_at(None)
    assert 'expiresAt' not in post.item

    # make sure that stuck in db
    post.refresh_item()
    assert 'expiresAt' not in post.item

    # check that the followed_first_story_manager was called correctly
    assert post.followed_first_story_manager.mock_calls == [
        call.refresh_after_story_change(story_prev=post_org_item, story_now=None),
    ]


def test_set(post, user):
    username = user.item['username']
    org_text = post.item['text']

    # verify starting values
    assert post.item['text'] == org_text
    assert post.item['textTags'] == []
    assert post.item.get('commentsDisabled', False) is False
    assert post.item.get('likesDisabled', False) is False
    assert post.item.get('verificationHidden', False) is False

    # do some edits
    new_text = f'its a new dawn, right @{user.item["username"]}, its a new day'
    post.set(text=new_text, comments_disabled=True, likes_disabled=True, verification_hidden=True)

    # verify new values
    assert post.item['text'] == new_text
    assert post.item['textTags'] == [{'tag': f'@{username}', 'userId': user.id}]
    assert post.item.get('commentsDisabled', False) is True
    assert post.item.get('likesDisabled', False) is True
    assert post.item.get('verificationHidden', False) is True

    # edit some params, ignore others
    post.set(likes_disabled=False)

    # verify only edited values changed
    assert post.item['text'] == new_text
    assert post.item['textTags'] == [{'tag': f'@{username}', 'userId': user.id}]
    assert post.item.get('commentsDisabled', False) is True
    assert post.item.get('likesDisabled', False) is False
    assert post.item.get('verificationHidden', False) is True


def test_set_cant_create_contentless_post(post_manager, post):
    org_text = post.item['text']

    # verify the post is text-only
    assert org_text
    assert list(post_manager.media_dynamo.generate_by_post(post.id)) == []

    # verify we can't set the text to null on that post
    with pytest.raises(post_manager.exceptions.PostException):
        post.set(text='')

    # check no changes anywhere
    assert post.item['text'] == org_text
    post.refresh_item()
    assert post.item['text'] == org_text


def test_set_text_to_null_media_post(post_manager, post_with_media):
    post = post_with_media
    org_text = post.item['text']

    # verify the post has media and text
    assert org_text
    assert list(post_manager.media_dynamo.generate_by_post(post.id))

    # verify we can null out the text on that post if we want
    post.set(text='')
    assert 'text' not in post.item
    assert 'textTags' not in post.item
    post.refresh_item()
    assert 'text' not in post.item
    assert 'textTags' not in post.item


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


def test_restore_completed_text_only_post_with_expiration(post_manager, post_with_expiration, user_manager):
    post = post_with_expiration
    posted_by_user_id = post.item['postedByUserId']
    posted_by_user = user_manager.get_user(posted_by_user_id)

    # archive the post
    post.archive()
    assert post.item['postStatus'] == PostStatus.ARCHIVED

    # check our starting post count
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 0

    # mock out some calls to far-flung other managers
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.feed_manager = Mock(FeedManager({}))

    # restore the post
    post.restore()
    assert post.item['postStatus'] == PostStatus.COMPLETED

    # check the post straight from the db
    post.refresh_item()
    assert post.item['postStatus'] == PostStatus.COMPLETED

    # check our post count - should have incremented
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 1

    # check calls to mocked out managers
    post.item['mediaObjects'] = []
    assert post.followed_first_story_manager.mock_calls == [
        call.refresh_after_story_change(story_now=post.item),
    ]
    assert post.feed_manager.mock_calls == [
        call.add_post_to_followers_feeds(posted_by_user_id, post.item),
    ]


def test_restore_pending_media_post(post_manager, post_with_media, user_manager):
    post = post_with_media
    posted_by_user_id = post.item['postedByUserId']
    posted_by_user = user_manager.get_user(posted_by_user_id)

    # archive the post
    post.archive()
    assert post.item['postStatus'] == PostStatus.ARCHIVED
    assert len(post.item['mediaObjects']) == 1
    assert post.item['mediaObjects'][0]['mediaStatus'] == MediaStatus.ARCHIVED

    # check our starting post count
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 0

    # mock out some calls to far-flung other managers
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.feed_manager = Mock(FeedManager({}))

    # restore the post
    post.restore()
    assert post.item['postStatus'] == PostStatus.PENDING
    assert len(post.item['mediaObjects']) == 1
    assert post.item['mediaObjects'][0]['mediaStatus'] == MediaStatus.AWAITING_UPLOAD

    # check the DB again
    post.refresh_item()
    assert post.item['postStatus'] == PostStatus.PENDING
    post_media_items = list(post_manager.media_dynamo.generate_by_post(post.id))
    assert len(post_media_items) == 1
    assert post_media_items[0]['mediaStatus'] == MediaStatus.AWAITING_UPLOAD

    # check our post count - should not have changed
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 0

    # check calls to mocked out managers
    assert post.followed_first_story_manager.mock_calls == []
    assert post.feed_manager.mock_calls == []


def test_restore_completed_media_post(post_manager, post_with_media, user_manager):
    post = post_with_media
    media = post_manager.media_manager.init_media(post_with_media.item['mediaObjects'][0])
    posted_by_user_id = post.item['postedByUserId']
    posted_by_user = user_manager.get_user(posted_by_user_id)

    # to look like a COMPLETED media post during the restore process,
    # we need to put objects in the mock s3 for all image sizes
    for size in MediaSize._ALL:
        media_path = media.get_s3_path(size)
        post_manager.clients['s3_uploads'].put_object(media_path, b'anything', 'application/octet-stream')

    # archive the post
    post.archive()
    assert post.item['postStatus'] == PostStatus.ARCHIVED
    assert len(post.item['mediaObjects']) == 1
    assert post.item['mediaObjects'][0]['mediaStatus'] == MediaStatus.ARCHIVED

    # check our starting post count
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 0

    # mock out some calls to far-flung other managers
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.feed_manager = Mock(FeedManager({}))

    # restore the post
    post.restore()
    assert post.item['postStatus'] == PostStatus.COMPLETED
    assert len(post.item['mediaObjects']) == 1
    assert post.item['mediaObjects'][0]['mediaStatus'] == MediaStatus.UPLOADED

    # check the DB again
    post.refresh_item()
    assert post.item['postStatus'] == PostStatus.COMPLETED
    media.refresh_item()
    assert media.item['mediaStatus'] == MediaStatus.UPLOADED

    # check our post count - should have incremented
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 1

    # check calls to mocked out managers
    post.item['mediaObjects'] = [media.item]
    assert post.followed_first_story_manager.mock_calls == []
    assert post.feed_manager.mock_calls == [
        call.add_post_to_followers_feeds(posted_by_user_id, post.item),
    ]


def test_delete_completed_text_only_post_with_expiration(post_manager, post_with_expiration, user_manager):
    post = post_with_expiration
    posted_by_user_id = post.item['postedByUserId']
    posted_by_user = user_manager.get_user(posted_by_user_id)

    # flag the post
    post.flag('flag_uid')
    assert post.item['flagCount'] == 1

    # check our starting post count
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 1

    # mock out some calls to far-flung other managers
    post.like_manager = Mock(LikeManager({}))
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.feed_manager = Mock(FeedManager({}))
    post.post_view_manager = Mock(PostViewManager({}))
    post.trending_manager = Mock(TrendingManager({'dynamo': {}}))

    # delete the post
    post.delete()
    assert post.item['postStatus'] == PostStatus.DELETING
    assert post.item['mediaObjects'] == []
    post_item = post.item

    # check the post has been unflagged
    assert list(post_manager.dynamo.generate_flag_items_by_post(post.id)) == []

    # check the post is no longer in the DB
    post.refresh_item()
    assert post.item is None

    # check our post count - should have decremented
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 0

    # check calls to mocked out managers
    assert post.like_manager.mock_calls == [
        call.dislike_all_of_post(post.id),
    ]
    assert post.followed_first_story_manager.mock_calls == [
        call.refresh_after_story_change(story_prev=post_item),
    ]
    assert post.feed_manager.mock_calls == [
        call.delete_post_from_followers_feeds(posted_by_user_id, post.id),
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


def test_delete_completed_media_post(post_manager, post_with_media, user_manager):
    post = post_with_media
    media = post_manager.media_manager.init_media(post_with_media.item['mediaObjects'][0])
    posted_by_user_id = post.item['postedByUserId']
    posted_by_user = user_manager.get_user(posted_by_user_id)

    # to look like a COMPLETED media post during the restore process,
    # we need to put objects in the mock s3 for all image sizes
    for size in MediaSize._ALL:
        media_path = media.get_s3_path(size)
        post_manager.clients['s3_uploads'].put_object(media_path, b'anything', 'application/octet-stream')

    # complete the post
    post.complete()
    assert post.item['postStatus'] == PostStatus.COMPLETED

    # check our starting post count
    posted_by_user.refresh_item()
    assert posted_by_user.item.get('postCount', 0) == 1

    # mock out some calls to far-flung other managers
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


def test_serailize(post, user_manager):
    expected_resp = post.item
    expected_resp['postedBy'] = user_manager.get_user(post.item['postedByUserId']).serialize()
    assert post.serialize() == expected_resp
