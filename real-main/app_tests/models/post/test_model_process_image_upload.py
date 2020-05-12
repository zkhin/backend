from unittest.mock import Mock, call

import pendulum
import pytest

from app.models.post.exceptions import PostException
from app.models.post.enums import PostStatus, PostType
from app.utils import image_size


@pytest.fixture
def user(user_manager, cognito_client):
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username='pbuid')
    yield user_manager.create_cognito_only_user('pbuid', 'pbUname')


@pytest.fixture
def text_only_post(post_manager, user):
    yield post_manager.add_post(user.id, 'pid1', PostType.TEXT_ONLY, text='t')


@pytest.fixture
def pending_post(post_manager, user):
    yield post_manager.add_post(user.id, 'pid2', PostType.IMAGE, text='t')


@pytest.fixture
def completed_post(post_manager, user, image_data_b64):
    yield post_manager.add_post(user.id, 'pid3', PostType.IMAGE, image_input={'imageData': image_data_b64})


def test_cant_process_image_upload_various_errors(post_manager, user, pending_post, text_only_post, completed_post):
    with pytest.raises(AssertionError, match='IMAGE'):
        text_only_post.process_image_upload()

    with pytest.raises(AssertionError, match='PENDING'):
        completed_post.process_image_upload()


def test_process_image_upload_exception_partway_thru_non_jpeg(pending_post):
    assert pending_post.item['postStatus'] == PostStatus.PENDING

    with pytest.raises(PostException, match='native.jpg image data not found'):
        pending_post.process_image_upload()
    assert pending_post.item['postStatus'] == PostStatus.PROCESSING

    pending_post.refresh_item()
    assert pending_post.item['postStatus'] == PostStatus.PROCESSING


def test_process_image_upload_success_jpeg(pending_post, s3_uploads_client, grant_data):
    post = pending_post
    assert post.item['postStatus'] == PostStatus.PENDING
    assert 'imageFormat' not in post.image_item

    # put some data in the mocked s3
    native_path = post.get_image_path(image_size.NATIVE)
    s3_uploads_client.put_object(native_path, grant_data, 'image/jpeg')

    # mock out a bunch of methods
    post.fill_native_jpeg_cache_from_heic = Mock(wraps=post.fill_native_jpeg_cache_from_heic)
    post.crop_native_jpeg_cache = Mock(wraps=post.crop_native_jpeg_cache)
    post.native_jpeg_cache.flush = Mock(wraps=post.native_jpeg_cache.flush)
    post.build_image_thumbnails = Mock(wraps=post.build_image_thumbnails)
    post.set_height_and_width = Mock(wraps=post.set_height_and_width)
    post.set_colors = Mock(wraps=post.set_colors)
    post.set_is_verified = Mock(wraps=post.set_is_verified)
    post.set_checksum = Mock(wraps=post.set_checksum)
    post.complete = Mock(wraps=post.complete)

    now = pendulum.now('utc')
    post.process_image_upload(now=now)

    # check the mocks were called correctly
    assert post.fill_native_jpeg_cache_from_heic.mock_calls == []
    assert post.crop_native_jpeg_cache.mock_calls == []
    assert post.native_jpeg_cache.flush.mock_calls == []
    assert post.build_image_thumbnails.mock_calls == [call()]
    assert post.set_height_and_width.mock_calls == [call()]
    assert post.set_colors.mock_calls == [call()]
    assert post.set_is_verified.mock_calls == [call()]
    assert post.set_checksum.mock_calls == [call()]
    assert post.complete.mock_calls == [call(now=now)]

    assert post.item['postStatus'] == PostStatus.COMPLETED
    post.refresh_item()
    assert post.item['postStatus'] == PostStatus.COMPLETED


def test_process_image_upload_with_crop(pending_post, s3_uploads_client, grant_data):
    post = pending_post
    assert post.item['postStatus'] == PostStatus.PENDING
    post.image_item['crop'] = {'upperLeft': {'x': 4, 'y': 2}, 'lowerRight': {'x': 102, 'y': 104}}

    # put some data in the mocked s3
    native_path = post.get_image_path(image_size.NATIVE)
    s3_uploads_client.put_object(native_path, grant_data, 'image/jpeg')

    # mock out a bunch of methods
    post.fill_native_jpeg_cache_from_heic = Mock(wraps=post.fill_native_jpeg_cache_from_heic)
    post.crop_native_jpeg_cache = Mock(wraps=post.crop_native_jpeg_cache)
    post.native_jpeg_cache.flush = Mock(wraps=post.native_jpeg_cache.flush)
    post.build_image_thumbnails = Mock(wraps=post.build_image_thumbnails)
    post.set_height_and_width = Mock(wraps=post.set_height_and_width)
    post.set_colors = Mock(wraps=post.set_colors)
    post.set_is_verified = Mock(wraps=post.set_is_verified)
    post.set_checksum = Mock(wraps=post.set_checksum)
    post.complete = Mock(wraps=post.complete)

    now = pendulum.now('utc')
    post.process_image_upload(now=now)

    # check the mocks were called correctly
    assert post.fill_native_jpeg_cache_from_heic.mock_calls == []
    assert post.crop_native_jpeg_cache.mock_calls == [call()]
    assert post.native_jpeg_cache.flush.mock_calls == [call()]
    assert post.build_image_thumbnails.mock_calls == [call()]
    assert post.set_height_and_width.mock_calls == [call()]
    assert post.set_colors.mock_calls == [call()]
    assert post.set_is_verified.mock_calls == [call()]
    assert post.set_checksum.mock_calls == [call()]
    assert post.complete.mock_calls == [call(now=now)]

    assert post.item['postStatus'] == PostStatus.COMPLETED
    post.refresh_item()
    assert post.item['postStatus'] == PostStatus.COMPLETED


def test_process_image_upload_success_heic_with_crop(pending_post, s3_uploads_client, heic_data):
    post = pending_post
    assert post.item['postStatus'] == PostStatus.PENDING
    post.image_item['imageFormat'] = 'HEIC'
    post.image_item['crop'] = {'upperLeft': {'x': 4, 'y': 2}, 'lowerRight': {'x': 102, 'y': 104}}

    # put some data in the mocked s3
    native_path = post.get_image_path(image_size.NATIVE_HEIC)
    s3_uploads_client.put_object(native_path, heic_data, 'image/heic')

    # mock out a bunch of methods
    post.fill_native_jpeg_cache_from_heic = Mock(wraps=post.fill_native_jpeg_cache_from_heic)
    post.crop_native_jpeg_cache = Mock(wraps=post.crop_native_jpeg_cache)
    post.native_jpeg_cache.flush = Mock(wraps=post.native_jpeg_cache.flush)
    post.build_image_thumbnails = Mock(wraps=post.build_image_thumbnails)
    post.set_height_and_width = Mock(wraps=post.set_height_and_width)
    post.set_colors = Mock(wraps=post.set_colors)
    post.set_is_verified = Mock(wraps=post.set_is_verified)
    post.set_checksum = Mock(wraps=post.set_checksum)
    post.complete = Mock(wraps=post.complete)

    now = pendulum.now('utc')
    post.process_image_upload(now=now)

    # check the mocks were called correctly
    assert post.fill_native_jpeg_cache_from_heic.mock_calls == [call()]
    assert post.crop_native_jpeg_cache.mock_calls == [call()]
    assert post.native_jpeg_cache.flush.mock_calls == [call()]
    assert post.build_image_thumbnails.mock_calls == [call()]
    assert post.set_height_and_width.mock_calls == [call()]
    assert post.set_colors.mock_calls == [call()]
    assert post.set_is_verified.mock_calls == [call()]
    assert post.set_checksum.mock_calls == [call()]
    assert post.complete.mock_calls == [call(now=now)]

    assert post.item['postStatus'] == PostStatus.COMPLETED
    post.refresh_item()
    assert post.item['postStatus'] == PostStatus.COMPLETED
