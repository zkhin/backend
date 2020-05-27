import base64
import decimal
import logging
import os.path as path
import unittest.mock as mock
import uuid

import pendulum
import pytest

from app.models import FollowedFirstStoryManager
from app.models.post.enums import PostType, PostStatus
from app.models.post.model import Post
from app.utils import image_size


grant_height = 320
grant_width = 240
grant_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'grant.jpg')
blank_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'big-blank.jpg')

heic_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'IMG_0265.HEIC')
heic_width = 4032
heic_height = 3024

grant_colors = [
    {'r': 51, 'g': 58, 'b': 45},
    {'r': 186, 'g': 206, 'b': 228},
    {'r': 145, 'g': 154, 'b': 169},
    {'r': 158, 'g': 180, 'b': 205},
    {'r': 130, 'g': 123, 'b': 125},
]


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user, 'pid1', PostType.TEXT_ONLY, text='t')


@pytest.fixture
def pending_video_post(post_manager, user2):
    yield post_manager.add_post(user2, 'pidv1', PostType.VIDEO)


@pytest.fixture
def pending_image_post(post_manager, user2):
    yield post_manager.add_post(user2, 'pidi1', PostType.IMAGE)


@pytest.fixture
def pending_image_post_heic(post_manager, user2):
    yield post_manager.add_post(user2, 'pid2', PostType.IMAGE, image_input={'imageFormat': 'HEIC'})


@pytest.fixture
def processing_video_post(pending_video_post, s3_uploads_client, grant_data):
    post = pending_video_post
    transacts = [post.dynamo.transact_set_post_status(post.item, PostStatus.PROCESSING)]
    post.dynamo.client.transact_write_items(transacts)
    post.refresh_item()
    image_path = post.get_image_path(image_size.NATIVE)
    s3_uploads_client.put_object(image_path, grant_data, 'image/jpeg')
    yield post


@pytest.fixture
def completed_video_post(processing_video_post):
    # Note: lacks the actual video files
    post = processing_video_post
    post.build_image_thumbnails()
    post.complete()
    yield post


@pytest.fixture
def albums(album_manager, user2):
    album1 = album_manager.add_album(user2.id, 'aid-1', 'album name')
    album2 = album_manager.add_album(user2.id, 'aid-2', 'album name')
    yield [album1, album2]


@pytest.fixture
def post_with_expiration(post_manager, user2):
    yield post_manager.add_post(
        user2, 'pid2', PostType.TEXT_ONLY, text='t', lifetime_duration=pendulum.duration(hours=1),
    )


@pytest.fixture
def post_with_media(post_manager, user2, image_data_b64):
    yield post_manager.add_post(user2, 'pid', PostType.IMAGE, image_input={'imageData': image_data_b64}, text='t')


def test_refresh_item(post):
    # go behind their back and edit the post in the DB
    new_post_item = post.dynamo.increment_viewed_by_count(post.id)
    assert new_post_item != post.item

    # now refresh the item, and check they now do match
    post.refresh_item()
    assert new_post_item == post.item


def test_get_original_video_path(post):
    user_id = post.item['postedByUserId']
    post_id = post.id

    video_path = post.get_original_video_path()
    assert video_path == f'{user_id}/post/{post_id}/video-original.mov'


def test_get_video_writeonly_url(cloudfront_client, s3_uploads_client):
    item = {
        'postedByUserId': 'user-id',
        'postId': 'post-id',
        'postType': PostType.VIDEO,
        'postStatus': PostStatus.PENDING,
    }
    expected_url = {}
    cloudfront_client.configure_mock(**{
        'generate_presigned_url.return_value': expected_url,
    })

    post = Post(item, cloudfront_client=cloudfront_client, s3_uploads_client=s3_uploads_client)
    url = post.get_video_writeonly_url()
    assert url == expected_url

    expected_path = 'user-id/post/post-id/video-original.mov'
    assert cloudfront_client.mock_calls == [mock.call.generate_presigned_url(expected_path, ['PUT'])]


def test_get_image_readonly_url(cloudfront_client, s3_uploads_client):
    item = {
        'postedByUserId': 'user-id',
        'postId': 'post-id',
        'postType': PostType.IMAGE,
        'postStatus': PostStatus.PENDING,
    }
    expected_url = {}
    cloudfront_client.configure_mock(**{
        'generate_presigned_url.return_value': expected_url,
    })

    post = Post(item, cloudfront_client=cloudfront_client, s3_uploads_client=s3_uploads_client)
    url = post.get_image_readonly_url(image_size.NATIVE)
    assert url == expected_url

    expected_path = f'user-id/post/post-id/image/{image_size.NATIVE.filename}'
    assert cloudfront_client.mock_calls == [mock.call.generate_presigned_url(expected_path, ['GET', 'HEAD'])]


def test_get_hls_access_cookies(cloudfront_client, s3_uploads_client):
    user_id = 'uid'
    post_id = 'pid'
    item = {
        'postedByUserId': user_id,
        'postId': post_id,
        'postType': PostType.VIDEO,
        'postStatus': PostStatus.COMPLETED,
    }
    domain = 'cf-domain'
    expires_at = pendulum.now('utc')
    presigned_cookies = {
        'ExpiresAt': expires_at.to_iso8601_string(),
        'CloudFront-Policy': 'cf-policy',
        'CloudFront-Signature': 'cf-signature',
        'CloudFront-Key-Pair-Id': 'cf-kpid',
    }
    cloudfront_client.configure_mock(**{
        'generate_presigned_cookies.return_value': presigned_cookies,
        'domain': domain,
    })

    post = Post(item, cloudfront_client=cloudfront_client, s3_uploads_client=s3_uploads_client)
    access_cookies = post.get_hls_access_cookies()

    assert access_cookies == {
        'domain': domain,
        'path': f'/{user_id}/post/{post_id}/video-hls/',
        'expiresAt': expires_at.to_iso8601_string(),
        'policy': 'cf-policy',
        'signature': 'cf-signature',
        'keyPairId': 'cf-kpid',
    }

    cookie_path = f'{user_id}/post/{post_id}/video-hls/video*'
    assert cloudfront_client.mock_calls == [mock.call.generate_presigned_cookies(cookie_path)]


def test_delete_s3_video(s3_uploads_client):
    post_item = {
        'postedByUserId': 'uid',
        'postId': 'pid',
        'postType': PostType.VIDEO,
    }
    post = Post(post_item, s3_uploads_client=s3_uploads_client)
    path = post.get_original_video_path()
    assert s3_uploads_client.exists(path) is False

    # even with video in s3 should not error out
    post.delete_s3_video()
    assert s3_uploads_client.exists(path) is False

    # put some data up there
    s3_uploads_client.put_object(path, b'data', 'application/octet-stream')
    assert s3_uploads_client.exists(path) is True

    # delete it, verify it's gone
    post.delete_s3_video()
    assert s3_uploads_client.exists(path) is False


def test_set_checksum(post):
    assert 'checksum' not in post.item

    # put some content with a known md5 up in s3
    content = b'anything'
    md5 = 'f0e166dc34d14d6c228ffac576c9a43c'
    path = post.get_image_path(image_size.NATIVE)
    post.s3_uploads_client.put_object(path, content, 'application/octet-stream')

    # set the checksum, check what was saved to the DB
    post.set_checksum()
    assert post.item['checksum'] == md5
    post.refresh_item()
    assert post.item['checksum'] == md5


def test_set_is_verified_minimal(pending_image_post):
    # check initial state and configure mock
    post = pending_image_post
    assert 'isVerified' not in post.item
    post.post_verification_client = mock.Mock(**{'verify_image.return_value': False})

    # do the call, check final state
    post.set_is_verified()
    assert post.item['isVerified'] is False
    post.refresh_item()
    assert post.item['isVerified'] is False

    # check mock called correctly
    assert post.post_verification_client.mock_calls == [mock.call.verify_image(
        post.get_image_readonly_url(image_size.NATIVE), image_format=None, original_format=None, taken_in_real=None
    )]


def test_set_is_verified_maximal(pending_image_post):
    # check initial state and configure mock
    post = pending_image_post
    assert 'isVerified' not in post.item
    post.post_verification_client = mock.Mock(**{'verify_image.return_value': True})
    post.image_item['imageFormat'] = 'ii'
    post.image_item['originalFormat'] = 'oo'
    post.image_item['takenInReal'] = False

    # do the call, check final state
    post.set_is_verified()
    assert post.item['isVerified'] is True
    post.refresh_item()
    assert post.item['isVerified'] is True

    # check mock called correctly
    assert post.post_verification_client.mock_calls == [mock.call.verify_image(
        post.get_image_readonly_url(image_size.NATIVE), image_format='ii', original_format='oo', taken_in_real=False
    )]


def test_set_expires_at(post):
    # add a post without an expires at
    assert 'expiresAt' not in post.item

    # set the expires at to something
    now = pendulum.now('utc')
    post.followed_first_story_manager = mock.Mock(FollowedFirstStoryManager({}))
    post.set_expires_at(now)
    assert post.item['expiresAt'] == now.to_iso8601_string()

    # make sure that stuck in db
    post.refresh_item()
    assert post.item['expiresAt'] == now.to_iso8601_string()

    # check that the followed_first_story_manager was called correctly
    assert post.followed_first_story_manager.mock_calls == [
        mock.call.refresh_after_story_change(story_prev=None, story_now=post.item),
    ]

    # set the expires at to something else
    post.followed_first_story_manager.reset_mock()
    now = pendulum.now('utc')
    post_org_item = post.item.copy()
    post.set_expires_at(now)
    assert post.item['expiresAt'] == now.to_iso8601_string()

    # make sure that stuck in db
    post.refresh_item()
    assert post.item['expiresAt'] == now.to_iso8601_string()

    # check that the followed_first_story_manager was called correctly
    assert post.followed_first_story_manager.mock_calls == [
        mock.call.refresh_after_story_change(story_prev=post_org_item, story_now=post.item),
    ]


def test_clear_expires_at(post_with_expiration):
    # add a post with an expires at
    post = post_with_expiration
    assert 'expiresAt' in post.item

    # remove the expires at
    post.followed_first_story_manager = mock.Mock(FollowedFirstStoryManager({}))
    post_org_item = post.item.copy()
    post.set_expires_at(None)
    assert 'expiresAt' not in post.item

    # make sure that stuck in db
    post.refresh_item()
    assert 'expiresAt' not in post.item

    # check that the followed_first_story_manager was called correctly
    assert post.followed_first_story_manager.mock_calls == [
        mock.call.refresh_after_story_change(story_prev=post_org_item, story_now=None),
    ]


def test_upload_native_image_data_base64(pending_image_post):
    post = pending_image_post
    native_path = post.get_image_path(image_size.NATIVE)
    image_data = b'imagedatahere'
    image_data_b64 = base64.b64encode(image_data)

    # mark the post a processing (in mem sufficient)
    post.item['postStatus'] = PostStatus.PROCESSING

    # check no data on post, nor in s3
    assert not hasattr(post, '_native_jpeg_data')
    with pytest.raises(post.s3_uploads_client.exceptions.NoSuchKey):
        assert post.s3_uploads_client.get_object_data_stream(native_path)

    # put data up there
    post.upload_native_image_data_base64(image_data_b64)

    # check it was placed in mem and in s3
    assert post.native_jpeg_cache.get_fh().read() == image_data
    assert post.s3_uploads_client.get_object_data_stream(native_path).read() == image_data


def test_set(post, user):
    username = user.item['username']
    org_text = post.item['text']

    # verify starting values
    assert post.item['text'] == org_text
    assert post.item['textTags'] == []
    assert post.item.get('commentsDisabled', False) is False
    assert post.item.get('likesDisabled', False) is False
    assert post.item.get('sharingDisabled', False) is False
    assert post.item.get('verificationHidden', False) is False

    # do some edits
    new_text = f'its a new dawn, right @{user.item["username"]}, its a new day'
    post.set(text=new_text, comments_disabled=True, likes_disabled=True, sharing_disabled=True,
             verification_hidden=True)

    # verify new values
    assert post.item['text'] == new_text
    assert post.item['textTags'] == [{'tag': f'@{username}', 'userId': user.id}]
    assert post.item.get('commentsDisabled', False) is True
    assert post.item.get('likesDisabled', False) is True
    assert post.item.get('sharingDisabled', False) is True
    assert post.item.get('verificationHidden', False) is True

    # edit some params, ignore others
    post.set(likes_disabled=False, verification_hidden=False)

    # verify only edited values changed
    assert post.item['text'] == new_text
    assert post.item['textTags'] == [{'tag': f'@{username}', 'userId': user.id}]
    assert post.item.get('commentsDisabled', False) is True
    assert post.item.get('likesDisabled', False) is False
    assert post.item.get('sharingDisabled', False) is True
    assert post.item.get('verificationHidden', False) is False


def test_set_cant_create_contentless_post(post_manager, post):
    org_text = post.item['text']

    # verify the post is text-only
    assert org_text
    assert post.image_item is None

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
    assert post.image_item

    # verify we can null out the text on that post if we want
    post.set(text='')
    assert 'text' not in post.item
    assert 'textTags' not in post.item
    post.refresh_item()
    assert 'text' not in post.item
    assert 'textTags' not in post.item


def test_serailize(user, post, user_manager):
    resp = post.serialize('caller-uid')
    assert resp.pop('postedBy')['userId'] == user.id
    assert resp == post.item


def test_error_failure(post_manager, post):
    # verify can't change a completed post to error
    with pytest.raises(post_manager.exceptions.PostException, match='PENDING'):
        post.error()


def test_error_pending_post(post_manager, user):
    # create a pending post
    post = post_manager.add_post(user, 'pid2', PostType.IMAGE)
    assert post.item['postStatus'] == PostStatus.PENDING

    # error it out, verify in-mem copy got marked as such
    post.error()
    assert post.item['postStatus'] == PostStatus.ERROR

    # verify error state saved to DB
    post.refresh_item()
    assert post.item['postStatus'] == PostStatus.ERROR


def test_error_processing_post(post_manager, user):
    # create a pending post
    post = post_manager.add_post(user, 'pid2', PostType.IMAGE)

    # manually mark the Post as being processed
    transacts = [post.dynamo.transact_set_post_status(post.item, PostStatus.PROCESSING)]
    post.dynamo.client.transact_write_items(transacts)

    post.refresh_item()
    assert post.item['postStatus'] == PostStatus.PROCESSING

    # error it out, verify in-mem copy got marked as such
    post.error()
    assert post.item['postStatus'] == PostStatus.ERROR

    # verify error state saved to DB
    post.refresh_item()
    assert post.item['postStatus'] == PostStatus.ERROR


def test_set_album_errors(album_manager, post_manager, user_manager, post, post_with_media, user):
    # album doesn't exist
    with pytest.raises(post_manager.exceptions.PostException, match='does not exist'):
        post_with_media.set_album('aid-dne')

    # album is owned by a different user
    album = album_manager.add_album(user.id, 'aid-2', 'album name')
    with pytest.raises(post_manager.exceptions.PostException, match='belong to different users'):
        post_with_media.set_album(album.id)


def test_set_album_completed_post(albums, post_with_media):
    post = post_with_media
    album1, album2 = albums

    # verify starting state
    assert 'albumId' not in post.item
    assert album1.item.get('postCount', 0) == 0
    assert album2.item.get('postCount', 0) == 0
    assert album1.item.get('rankCount', 0) == 0
    assert album2.item.get('rankCount', 0) == 0
    assert 'artHash' not in album1.item
    assert 'artHash' not in album2.item

    # go from no album to an album
    post.set_album(album1.id)
    assert post.item['albumId'] == album1.id
    assert post.item['gsiK3SortKey'] == 0   # album rank
    album1.refresh_item()
    assert album1.item.get('postCount', 0) == 1
    assert album1.item.get('rankCount', 0) == 1
    assert album1.item['artHash']
    album2.refresh_item()
    assert album2.item.get('postCount', 0) == 0
    assert album2.item.get('rankCount', 0) == 0
    assert 'artHash' not in album2.item

    # change the album
    post.set_album(album2.id)
    assert post.item['albumId'] == album2.id
    assert post.item['gsiK3SortKey'] == 0   # album rank
    album1.refresh_item()
    assert album1.item.get('postCount', 0) == 0
    assert album1.item.get('rankCount', 0) == 1
    assert 'artHash' not in album1.item
    album2.refresh_item()
    assert album2.item.get('postCount', 0) == 1
    assert album2.item.get('rankCount', 0) == 1
    assert album2.item['artHash']

    # no-op
    post.set_album(album2.id)
    assert post.item['albumId'] == album2.id
    assert post.item['gsiK3SortKey'] == 0   # album rank
    album1.refresh_item()
    assert album1.item.get('postCount', 0) == 0
    assert album1.item.get('rankCount', 0) == 1
    assert 'artHash' not in album1.item
    album2.refresh_item()
    assert album2.item.get('postCount', 0) == 1
    assert album2.item.get('rankCount', 0) == 1
    assert album2.item['artHash']

    # remove post from all albums
    post.set_album(None)
    assert 'albumId' not in post.item
    assert 'gsiK3SortKey' not in post.item
    album1.refresh_item()
    assert album1.item.get('postCount', 0) == 0
    assert album1.item.get('rankCount', 0) == 1
    assert 'artHash' not in album1.item
    album2.refresh_item()
    assert album2.item.get('postCount', 0) == 0
    assert album2.item.get('rankCount', 0) == 1
    assert 'artHash' not in album2.item

    # archive the post
    post.archive()

    # add it back to an album, should not increment counts
    post.set_album(album1.id)
    assert post.item['albumId'] == album1.id
    assert post.item['gsiK3SortKey'] == -1   # album rank
    album1.refresh_item()
    assert album1.item.get('postCount', 0) == 0
    assert album1.item.get('rankCount', 0) == 1
    assert 'artHash' not in album1.item


def test_set_album_text_post(post_manager, albums, user2):
    album1, album2 = albums
    post = post_manager.add_post(user2, 'pid', PostType.TEXT_ONLY, text='lore ipsum')

    # verify starting state
    assert 'albumId' not in post.item
    assert 'artHash' not in album1.item
    assert 'artHash' not in album2.item

    # go from no album to an album
    post.set_album(album1.id)
    assert post.item['albumId'] == album1.id
    assert post.item['gsiK3SortKey'] == 0   # album rank
    album1.refresh_item()
    assert album1.item['artHash']
    album2.refresh_item()
    assert 'artHash' not in album2.item

    # change the album
    post.set_album(album2.id)
    assert post.item['albumId'] == album2.id
    assert post.item['gsiK3SortKey'] == 0   # album rank
    album1.refresh_item()
    assert 'artHash' not in album1.item
    album2.refresh_item()
    assert album2.item['artHash']

    # remove post from all albums
    post.set_album(None)
    assert 'albumId' not in post.item
    assert 'gsiK3SortKey' not in post.item
    album1.refresh_item()
    assert 'artHash' not in album1.item
    album2.refresh_item()
    assert 'artHash' not in album2.item


def test_set_album_video_post(albums, user2, completed_video_post):
    post = completed_video_post
    album1, album2 = albums

    # verify starting state
    assert 'albumId' not in post.item
    assert 'artHash' not in album1.item
    assert 'artHash' not in album2.item

    # go from no album to an album
    post.set_album(album1.id)
    assert post.item['albumId'] == album1.id
    assert post.item['gsiK3SortKey'] == 0   # album rank
    album1.refresh_item()
    assert album1.item['artHash']
    album2.refresh_item()
    assert 'artHash' not in album2.item

    # change the album
    post.set_album(album2.id)
    assert post.item['albumId'] == album2.id
    assert post.item['gsiK3SortKey'] == 0   # album rank
    album1.refresh_item()
    assert 'artHash' not in album1.item
    album2.refresh_item()
    assert album2.item['artHash']

    # remove post from all albums
    post.set_album(None)
    assert 'albumId' not in post.item
    assert 'gsiK3SortKey' not in post.item
    album1.refresh_item()
    assert 'artHash' not in album1.item
    album2.refresh_item()
    assert 'artHash' not in album2.item


def test_set_album_order_failures(user, user2, albums, post_manager, image_data_b64):
    post1 = post_manager.add_post(user, 'pid1', PostType.IMAGE, image_input={'imageData': image_data_b64})
    post2 = post_manager.add_post(user2, 'pid2', PostType.IMAGE, image_input={'imageData': image_data_b64})
    post3 = post_manager.add_post(user2, 'pid3', PostType.IMAGE, image_input={'imageData': image_data_b64})
    post4 = post_manager.add_post(user2, 'pid4', PostType.IMAGE, image_input={'imageData': image_data_b64})
    album1, album2 = albums

    # put post2 & post3 in first album
    post2.set_album(album1.id)
    assert post2.item['albumId'] == album1.id
    assert post2.item['gsiK3SortKey'] == 0

    post3.set_album(album1.id)
    assert post3.item['albumId'] == album1.id
    assert post3.item['gsiK3SortKey'] == pytest.approx(decimal.Decimal(1 / 3))

    # put post4 in second album
    post4.set_album(album2.id)
    assert post4.item['albumId'] == album2.id
    assert post4.item['gsiK3SortKey'] == 0

    # verify can't change order with post that DNE
    with pytest.raises(post_manager.exceptions.PostException):
        post2.set_album_order('pid-dne')

    # verify can't change order using post from diff users
    with pytest.raises(post_manager.exceptions.PostException):
        post1.set_album_order(post2.id)
    with pytest.raises(post_manager.exceptions.PostException):
        post2.set_album_order(post1.id)

    # verify can't change order with posts in diff albums
    with pytest.raises(post_manager.exceptions.PostException):
        post4.set_album_order(post2.id)
    with pytest.raises(post_manager.exceptions.PostException):
        post2.set_album_order(post4.id)

    # verify *can* change order if everything correct
    post2.set_album_order(post3.id)
    assert post2.item['albumId'] == album1.id
    assert post2.item['gsiK3SortKey'] == decimal.Decimal(0.5)


def test_set_album_order_lots_of_set_middle(user2, albums, post_manager, image_data_b64):
    # album with three posts in it
    album, _ = albums
    post1 = post_manager.add_post(
        user2, 'pid1', PostType.IMAGE, image_input={'imageData': image_data_b64}, album_id=album.id,
    )
    post2 = post_manager.add_post(
        user2, 'pid2', PostType.IMAGE, image_input={'imageData': image_data_b64}, album_id=album.id,
    )
    post3 = post_manager.add_post(
        user2, 'pid3', PostType.IMAGE, image_input={'imageData': image_data_b64}, album_id=album.id,
    )

    # check starting state
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post1.id, post2.id, post3.id]
    assert post1.item['gsiK3SortKey'] == 0
    assert post2.item['gsiK3SortKey'] == pytest.approx(decimal.Decimal(1 / 3))
    assert post3.item['gsiK3SortKey'] == pytest.approx(decimal.Decimal(1 / 2))

    # change middle post, check order
    post3.set_album_order(post1.id)
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post1.id, post3.id, post2.id]
    assert post3.item['gsiK3SortKey'] == pytest.approx(decimal.Decimal(1 / 6))

    # change middle post, check order
    post2.set_album_order(post1.id)
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post1.id, post2.id, post3.id]
    assert post2.item['gsiK3SortKey'] == pytest.approx(decimal.Decimal(1 / 12))

    # change middle post, check order
    post3.set_album_order(post1.id)
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post1.id, post3.id, post2.id]
    assert post3.item['gsiK3SortKey'] == pytest.approx(decimal.Decimal(1 / 24))

    # change middle post, check order
    post2.set_album_order(post1.id)
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post1.id, post2.id, post3.id]
    assert post2.item['gsiK3SortKey'] == pytest.approx(decimal.Decimal(1 / 48))


def test_set_album_order_lots_of_set_front(user2, albums, post_manager, image_data_b64):
    # album with two posts in it
    album, _ = albums
    post1 = post_manager.add_post(
        user2, 'pid1', PostType.IMAGE, image_input={'imageData': image_data_b64}, album_id=album.id,
    )
    post2 = post_manager.add_post(
        user2, 'pid2', PostType.IMAGE, image_input={'imageData': image_data_b64}, album_id=album.id,
    )

    # check starting state
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post1.id, post2.id]
    assert post1.item['gsiK3SortKey'] == 0
    assert post2.item['gsiK3SortKey'] == pytest.approx(decimal.Decimal(1 / 3))

    # change first post, check order
    post2.set_album_order(None)
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post2.id, post1.id]
    assert post2.item['gsiK3SortKey'] == pytest.approx(decimal.Decimal(-2 / 4))

    # change first post, check order
    post1.set_album_order(None)
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post1.id, post2.id]
    assert post1.item['gsiK3SortKey'] == pytest.approx(decimal.Decimal(-3 / 5))

    # change first post, check order
    post2.set_album_order(None)
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post2.id, post1.id]
    assert post2.item['gsiK3SortKey'] == pytest.approx(decimal.Decimal(-4 / 6))


def test_set_album_order_lots_of_set_back(user2, albums, post_manager, image_data_b64):
    # album with two posts in it
    album, _ = albums
    post1 = post_manager.add_post(
        user2, 'pid1', PostType.IMAGE, image_input={'imageData': image_data_b64}, album_id=album.id,
    )
    post2 = post_manager.add_post(
        user2, 'pid2', PostType.IMAGE, image_input={'imageData': image_data_b64}, album_id=album.id,
    )

    # check starting state
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post1.id, post2.id]
    assert post1.item['gsiK3SortKey'] == 0
    assert post2.item['gsiK3SortKey'] == pytest.approx(decimal.Decimal(1 / 3))

    # change last post, check order
    post1.set_album_order(post2.id)
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post2.id, post1.id]
    assert post1.item['gsiK3SortKey'] == pytest.approx(decimal.Decimal(2 / 4))

    # change last post, check order
    post2.set_album_order(post1.id)
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post1.id, post2.id]
    assert post2.item['gsiK3SortKey'] == pytest.approx(decimal.Decimal(3 / 5))

    # change last post, check order
    post1.set_album_order(post2.id)
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post2.id, post1.id]
    assert post1.item['gsiK3SortKey'] == pytest.approx(decimal.Decimal(4 / 6))


def test_build_image_thumbnails_video_post(user, processing_video_post, s3_uploads_client):
    post = processing_video_post

    # check starting state
    assert s3_uploads_client.exists(post.get_image_path(image_size.NATIVE))
    assert not s3_uploads_client.exists(post.get_image_path(image_size.K4))
    assert not s3_uploads_client.exists(post.get_image_path(image_size.P1080))
    assert not s3_uploads_client.exists(post.get_image_path(image_size.P480))
    assert not s3_uploads_client.exists(post.get_image_path(image_size.P64))

    # build the thumbnails
    post.build_image_thumbnails()

    # check final state
    assert s3_uploads_client.exists(post.get_image_path(image_size.NATIVE))
    assert s3_uploads_client.exists(post.get_image_path(image_size.K4))
    assert s3_uploads_client.exists(post.get_image_path(image_size.P1080))
    assert s3_uploads_client.exists(post.get_image_path(image_size.P480))
    assert s3_uploads_client.exists(post.get_image_path(image_size.P64))


def test_get_image_writeonly_url(pending_image_post, cloudfront_client, dynamo_client):
    post = pending_image_post
    post.cloudfront_client = cloudfront_client

    # check a jpg image post
    assert post.get_image_writeonly_url()
    assert 'native.jpg' in cloudfront_client.generate_presigned_url.call_args.args[0]
    assert 'native.heic' not in cloudfront_client.generate_presigned_url.call_args.args[0]

    # set the imageFormat to heic
    query_kwargs = {
        'Key': {
            'partitionKey': f'post/{post.id}',
            'sortKey': 'image',
        },
        'UpdateExpression': 'SET imageFormat = :im',
        'ExpressionAttributeValues': {':im': 'HEIC'},
    }
    dynamo_client.update_item(query_kwargs)
    post.refresh_image_item()

    # check a heic image post
    assert post.get_image_writeonly_url()
    assert 'native.jpg' not in cloudfront_client.generate_presigned_url.call_args.args[0]
    assert 'native.heic' in cloudfront_client.generate_presigned_url.call_args.args[0]


def test_fill_native_jpeg_cache_from_heic(pending_image_post, s3_uploads_client):
    post = pending_image_post

    # put the heic image in the bucket
    s3_heic_path = post.get_image_path(image_size.NATIVE_HEIC)
    s3_uploads_client.put_object(s3_heic_path, open(heic_path, 'rb'), 'image/heic')

    # verify there's no native jpeg
    s3_jpeg_path = post.get_image_path(image_size.NATIVE)
    assert not s3_uploads_client.exists(s3_jpeg_path)

    post.fill_native_jpeg_cache_from_heic()

    # verify the jpeg cache is now full, of the correct size, and s3 has not been filled
    assert not post.native_jpeg_cache.is_empty
    assert not post.native_jpeg_cache.is_synced
    assert post.native_jpeg_cache.get_image().size == (heic_width, heic_height)
    assert not s3_uploads_client.exists(s3_jpeg_path)


def test_fill_native_jpeg_cache_from_heic_bad_heic_data(pending_image_post, s3_uploads_client):
    post = pending_image_post

    # put some non-heic data in the heic spot
    s3_heic_path = post.get_image_path(image_size.NATIVE_HEIC)
    s3_uploads_client.put_object(s3_heic_path, b'notheicdata', 'image/heic')

    # verify there's no native jpeg
    s3_jpeg_path = post.get_image_path(image_size.NATIVE)
    assert not s3_uploads_client.exists(s3_jpeg_path)

    with pytest.raises(post.exceptions.PostException, match='Unable to read HEIC'):
        post.fill_native_jpeg_cache_from_heic()

    # verify there's still no native jpeg
    assert post.native_jpeg_cache.is_empty
    assert not s3_uploads_client.exists(s3_jpeg_path)


def test_set_height_and_width(s3_uploads_client, pending_image_post):
    post = pending_image_post
    assert 'height' not in post.image_item
    assert 'width' not in post.image_item

    # put an image in the bucket
    s3_path = post.get_image_path(image_size.NATIVE)
    s3_uploads_client.put_object(s3_path, open(grant_path, 'rb'), 'image/jpeg')

    post.set_height_and_width()
    assert post.image_item['height'] == grant_height
    assert post.image_item['width'] == grant_width
    post.refresh_image_item()
    assert post.image_item['height'] == grant_height
    assert post.image_item['width'] == grant_width


def test_set_colors(s3_uploads_client, pending_image_post):
    post = pending_image_post
    assert 'colors' not in post.image_item

    # put an image in the bucket
    s3_path = post.get_image_path(image_size.NATIVE)
    s3_uploads_client.put_object(s3_path, open(grant_path, 'rb'), 'image/jpeg')

    post.set_colors()
    assert post.image_item['colors'] == grant_colors


def test_set_colors_colortheif_fails(s3_uploads_client, pending_image_post, caplog):
    post = pending_image_post
    assert 'colors' not in post.image_item

    # put an image in the bucket
    s3_path = post.get_image_path(image_size.NATIVE)
    s3_uploads_client.put_object(s3_path, open(blank_path, 'rb'), 'image/jpeg')

    assert len(caplog.records) == 0
    with caplog.at_level(logging.WARNING):
        post.set_colors()
        assert 'colors' not in post.image_item

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == 'WARNING'
    assert 'ColorTheif' in caplog.records[0].msg
    assert f'`{post.id}`' in caplog.records[0].msg
