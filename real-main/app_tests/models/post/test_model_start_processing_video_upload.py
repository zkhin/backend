from unittest.mock import call

import pytest

from app.models.post.enums import PostStatus, PostType


@pytest.fixture
def user(user_manager):
    yield user_manager.create_cognito_only_user('pbuid', 'pbUname')


@pytest.fixture
def pending_video_post(post_manager, user):
    yield post_manager.add_post(user.id, 'pid-v', PostType.VIDEO)


def test_cant_start_processing_video_upload_various_errors(post_manager, user, pending_video_post):
    text_only_post = post_manager.add_post(user.id, 'pid-to', PostType.TEXT_ONLY, text='t')
    with pytest.raises(AssertionError, match='VIDEO'):
        text_only_post.start_processing_video_upload()

    image_post = post_manager.add_post(user.id, 'pid-i', PostType.IMAGE, media_uploads=[{'mediaId': 'mid1'}])
    with pytest.raises(AssertionError, match='VIDEO'):
        image_post.start_processing_video_upload()

    transacts = [post_manager.dynamo.transact_set_post_status(pending_video_post.item, PostStatus.COMPLETED)]
    post_manager.dynamo.client.transact_write_items(transacts)
    completed_post = pending_video_post.refresh_item()
    with pytest.raises(AssertionError, match='PENDING'):
        completed_post.start_processing_video_upload()


def test_start_processing_video_upload_exception_partway_thru(pending_video_post, mediaconvert_client):
    assert pending_video_post.item['postStatus'] == PostStatus.PENDING

    # mock the mediaconvert api so it throws an error
    pending_video_post.mediaconvert_client = mediaconvert_client
    pending_video_post.mediaconvert_client.configure_mock(**{
        'create_job.side_effect': Exception('stuff went wrong')
    })

    with pytest.raises(Exception):
        pending_video_post.start_processing_video_upload()

    # check video post is left in 'processing' state
    assert pending_video_post.item['postStatus'] == PostStatus.PROCESSING
    pending_video_post.refresh_item()
    assert pending_video_post.item['postStatus'] == PostStatus.PROCESSING


def test_start_processing_video_upload_success(pending_video_post, mediaconvert_client):
    assert pending_video_post.item['postStatus'] == PostStatus.PENDING

    # mock the mediaconvert api
    pending_video_post.mediaconvert_client = mediaconvert_client

    pending_video_post.start_processing_video_upload()

    # check the mock was called correctly
    input_s3_key = pending_video_post.get_original_video_path()
    video_output_s3_key_prefix = pending_video_post.get_hls_video_path_prefix()
    image_output_s3_key_prefix = pending_video_post.get_poster_video_path_prefix()
    assert pending_video_post.mediaconvert_client.mock_calls == [
        call.create_job(input_s3_key, video_output_s3_key_prefix, image_output_s3_key_prefix),
    ]

    # check video post is left in 'processing' state
    assert pending_video_post.item['postStatus'] == PostStatus.PROCESSING
    pending_video_post.refresh_item()
    assert pending_video_post.item['postStatus'] == PostStatus.PROCESSING
