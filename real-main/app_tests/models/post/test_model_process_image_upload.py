from unittest.mock import Mock, call

import pendulum
import pytest

from app.models.media.exceptions import MediaException
from app.models.post.enums import PostStatus, PostType


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

    with pytest.raises(MediaException, match='does not exist'):
        pending_post.process_image_upload()
    assert pending_post.item['postStatus'] == PostStatus.PROCESSING

    pending_post.refresh_item()
    assert pending_post.item['postStatus'] == PostStatus.PROCESSING


def test_process_image_upload_success(pending_post):
    assert pending_post.item['postStatus'] == PostStatus.PENDING

    # mock out a bunch of methods
    pending_post.media.set_height_and_width = Mock()
    pending_post.media.set_colors = Mock()
    pending_post.media.set_thumbnails = Mock()
    pending_post.is_native_image_jpeg = Mock(return_value=True)
    pending_post.set_is_verified = Mock()
    pending_post.set_checksum = Mock()
    pending_post.complete = Mock()

    now = pendulum.now('utc')
    pending_post.process_image_upload(now=now)

    # check the mocks were called correctly
    assert pending_post.media.set_height_and_width.mock_calls == [call()]
    assert pending_post.media.set_colors.mock_calls == [call()]
    assert pending_post.media.set_thumbnails.mock_calls == [call()]
    assert pending_post.set_is_verified.mock_calls == [call()]
    assert pending_post.set_checksum.mock_calls == [call()]
    assert pending_post.complete.mock_calls == [call(now=now)]

    assert pending_post.item['postStatus'] == PostStatus.PROCESSING  # we mocked out the call to complete()
    pending_post.refresh_item()
    assert pending_post.item['postStatus'] == PostStatus.PROCESSING  # we mocked out the call to complete()
