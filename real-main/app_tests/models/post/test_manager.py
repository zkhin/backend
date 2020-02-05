from datetime import datetime, timedelta

import pytest
from isodate.duration import Duration

from app.models.media.enums import MediaStatus
from app.models.post.enums import PostStatus


@pytest.fixture
def user(user_manager):
    yield user_manager.create_cognito_only_user('pbuid', 'pbUname')


@pytest.fixture
def posts(post_manager, user):
    post1 = post_manager.add_post(user.id, 'pid1', text='t')
    post2 = post_manager.add_post(user.id, 'pid2', text='t')
    yield (post1, post2)


@pytest.fixture
def album(album_manager, user):
    yield album_manager.add_album(user.id, 'aid', 'album name')


def test_get_post(post_manager, user_manager):
    # create a post behind the scenes
    post_id = 'pid'
    user = user_manager.create_cognito_only_user('pbuid', 'pbUname')
    post_manager.add_post(user.id, post_id, text='t')

    post = post_manager.get_post(post_id)
    assert post.id == post_id


def test_get_post_dne(post_manager):
    assert post_manager.get_post('pid-dne') is None


def test_add_post_errors(post_manager):
    # try to add a post without any content (no text or media)
    with pytest.raises(post_manager.exceptions.PostException) as error_info:
        post_manager.add_post('pbuid', 'pid')
    assert 'pbuid' in str(error_info.value)
    assert 'pid' in str(error_info.value)
    assert 'without text or media' in str(error_info.value)

    # try to add a post with a negative lifetime value
    with pytest.raises(post_manager.exceptions.PostException) as error_info:
        post_manager.add_post('pbuid', 'pid', text='t', lifetime_duration=Duration(hours=-1))
    assert 'pbuid' in str(error_info.value)
    assert 'pid' in str(error_info.value)
    assert 'negative lifetime' in str(error_info.value)

    # try to add a post with a zero lifetime value
    # note that isodate parses a parses the iso duration string P0D to timedelta(0),
    # not one of their duration objects
    with pytest.raises(post_manager.exceptions.PostException) as error_info:
        post_manager.add_post('pbuid', 'pid', text='t', lifetime_duration=timedelta(0))
    assert 'pbuid' in str(error_info.value)
    assert 'pid' in str(error_info.value)
    assert 'negative lifetime' in str(error_info.value)


def test_add_text_only_post(post_manager, user_manager):
    user_id = 'pbuid'
    post_id = 'pid'
    text = 'lore ipsum'
    now = datetime.utcnow()

    # add the post
    user_manager.create_cognito_only_user(user_id, 'pbUname')
    post_manager.add_post(user_id, post_id, text=text, now=now)

    # retrieve the post & media, check it
    post = post_manager.get_post(post_id)
    assert post.id == post_id
    assert post.item['postedByUserId'] == user_id
    assert post.item['postedAt'] == now.isoformat() + 'Z'
    assert post.item['text'] == 'lore ipsum'
    assert post.item['textTags'] == []
    assert post.item['postStatus'] == PostStatus.COMPLETED
    assert 'expiresAt' not in post.item
    assert list(post_manager.media_dynamo.generate_by_post(post_id)) == []


def test_add_text_with_tags_post(post_manager, user_manager):
    user_id = 'pbuid'
    username = 'pbUname'
    post_id = 'pid'
    text = 'Tagging you @pbUname!'

    # add the post
    user_manager.create_cognito_only_user(user_id, username)
    post_manager.add_post(user_id, post_id, text=text)

    # retrieve the post & media, check it
    post = post_manager.get_post(post_id)
    assert post.id == post_id
    assert post.item['text'] == text
    assert post.item['textTags'] == [{'tag': '@pbUname', 'userId': 'pbuid'}]


def test_add_post_album_errors(user_manager, post_manager, user, album):
    # can't create post with album that doesn't exist
    with pytest.raises(post_manager.exceptions.PostException):
        post_manager.add_post(user.id, 'pid-42', text='t', album_id='aid-dne')

    # can't create post in somebody else's album
    user2 = user_manager.create_cognito_only_user('uid-2', 'uname2')
    with pytest.raises(post_manager.exceptions.PostException):
        post_manager.add_post(user2.id, 'pid-42', text='t', album_id=album.id)


def test_add_media_post(post_manager):
    user_id = 'pbuid'
    post_id = 'pid'
    now = datetime.utcnow()
    media_id = 'mid'
    media_type = 'mtype'
    media_upload = {
        'mediaId': media_id,
        'mediaType': media_type,
    }

    # add the post (& media)
    post_manager.add_post(user_id, post_id, now=now, media_uploads=[media_upload])

    # retrieve the post & media, check it
    post = post_manager.get_post(post_id)
    assert post.id == post_id
    assert post.item['postedByUserId'] == user_id
    assert post.item['postedAt'] == now.isoformat() + 'Z'
    assert post.item['postStatus'] == PostStatus.PENDING
    assert 'text' not in post.item
    assert 'textTags' not in post.item
    assert 'expiresAt' not in post.item

    media_items = list(post_manager.media_dynamo.generate_by_post(post_id))
    assert len(media_items) == 1
    assert media_items[0]['mediaId'] == media_id
    assert media_items[0]['mediaType'] == media_type
    assert media_items[0]['postedAt'] == now.isoformat() + 'Z'
    assert media_items[0]['mediaStatus'] == MediaStatus.AWAITING_UPLOAD
    assert 'expiresAt' not in media_items[0]


def test_add_media_post_with_options(post_manager, album):
    user_id = 'pbuid'
    post_id = 'pid'
    text = 'lore ipsum'
    now = datetime.utcnow()
    media_id = 'mid'
    media_type = 'mtype'
    media_upload = {
        'mediaId': media_id,
        'mediaType': media_type,
        'takenInReal': False,
        'originalFormat': 'org-format',
    }
    lifetime_duration = Duration(hours=1)

    # add the post (& media)
    post_manager.add_post(
        user_id, post_id, text=text, now=now, media_uploads=[media_upload], lifetime_duration=lifetime_duration,
        album_id=album.id, comments_disabled=False, likes_disabled=True, verification_hidden=False,
    )
    expires_at = now + lifetime_duration

    # retrieve the post & media, check it
    post = post_manager.get_post(post_id)
    assert post.id == post_id
    assert post.item['postedByUserId'] == user_id
    assert post.item['albumId'] == album.id
    assert post.item['postedAt'] == now.isoformat() + 'Z'
    assert post.item['text'] == 'lore ipsum'
    assert post.item['postStatus'] == PostStatus.PENDING
    assert post.item['expiresAt'] == expires_at.isoformat() + 'Z'
    assert post.item['commentsDisabled'] is False
    assert post.item['likesDisabled'] is True
    assert post.item['verificationHidden'] is False

    media_items = list(post_manager.media_dynamo.generate_by_post(post_id))
    assert len(media_items) == 1
    assert media_items[0]['mediaId'] == media_id
    assert media_items[0]['mediaType'] == media_type
    assert media_items[0]['postedAt'] == now.isoformat() + 'Z'
    assert media_items[0]['mediaStatus'] == MediaStatus.AWAITING_UPLOAD
    assert media_items[0]['takenInReal'] is False
    assert media_items[0]['originalFormat'] == 'org-format'


def test_delete_recently_expired_posts(post_manager, user_manager, caplog):
    user = user_manager.create_cognito_only_user('pbuid', 'pbUname')
    now = datetime.utcnow()

    # create four posts with diff. expiration qualities
    post_no_expires = post_manager.add_post(user.id, 'pid1', text='t')
    assert 'expiresAt' not in post_no_expires.item

    post_future_expires = post_manager.add_post(user.id, 'pid2', text='t', lifetime_duration=Duration(hours=1))
    assert post_future_expires.item['expiresAt'] > now.isoformat() + 'Z'

    lifetime_duration = Duration(hours=now.hour, minutes=now.minute)
    post_expired_today = post_manager.add_post(user.id, 'pid3', text='t', lifetime_duration=lifetime_duration,
                                               now=(now - lifetime_duration))
    assert post_expired_today.item['expiresAt'] == now.isoformat() + 'Z'

    post_expired_last_week = post_manager.add_post(user.id, 'pid4', text='t', lifetime_duration=Duration(hours=1),
                                                   now=(now - Duration(days=7)))
    assert post_expired_last_week.item['expiresAt'] < (now - Duration(days=6)).isoformat() + 'Z'

    # run the deletion run
    post_manager.delete_recently_expired_posts()

    # check we logged one delete
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == 'WARNING'
    assert 'Deleting' in caplog.records[0].msg
    assert post_expired_today.id in caplog.records[0].msg

    # check one of the posts is missing from the DB, but the rest are still there
    assert post_no_expires.refresh_item().item
    assert post_future_expires.refresh_item().item
    assert post_expired_today.refresh_item().item is None
    assert post_expired_last_week.refresh_item().item


def test_delete_older_expired_posts(post_manager, user_manager, caplog):
    user = user_manager.create_cognito_only_user('pbuid', 'pbUname')
    now = datetime.utcnow()

    # create four posts with diff. expiration qualities
    post_no_expires = post_manager.add_post(user.id, 'pid1', text='t')
    assert 'expiresAt' not in post_no_expires.item

    post_future_expires = post_manager.add_post(user.id, 'pid2', text='t', lifetime_duration=Duration(hours=1))
    assert post_future_expires.item['expiresAt'] > now.isoformat() + 'Z'

    lifetime_duration = Duration(hours=now.hour, minutes=now.minute)
    post_expired_today = post_manager.add_post(user.id, 'pid3', text='t', lifetime_duration=lifetime_duration,
                                               now=(now - lifetime_duration))
    assert post_expired_today.item['expiresAt'] == now.isoformat() + 'Z'

    post_expired_last_week = post_manager.add_post(user.id, 'pid4', text='t', lifetime_duration=Duration(hours=1),
                                                   now=(now - Duration(days=7)))
    assert post_expired_last_week.item['expiresAt'] < (now - Duration(days=6)).isoformat() + 'Z'

    # run the deletion run
    post_manager.delete_older_expired_posts()

    # check we logged one delete
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == 'WARNING'
    assert 'Deleting' in caplog.records[0].msg
    assert post_expired_last_week.id in caplog.records[0].msg

    # check one of the posts is missing from the DB, but the rest are still there
    assert post_no_expires.refresh_item().item
    assert post_future_expires.refresh_item().item
    assert post_expired_today.refresh_item().item
    assert post_expired_last_week.refresh_item().item is None
