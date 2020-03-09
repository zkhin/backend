from os import path

import pytest

from app.models.post.enums import PostStatus, PostType
from app.utils import image_size

grant_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'grant.jpg')


@pytest.fixture
def user(user_manager):
    yield user_manager.create_cognito_only_user('pbuid', 'pbUname')


@pytest.fixture
def pending_video_post(post_manager, user):
    yield post_manager.add_post(user.id, 'pid-v', PostType.VIDEO)


@pytest.fixture
def processing_video_post(pending_video_post, s3_uploads_client):
    post = pending_video_post
    transacts = [post.dynamo.transact_set_post_status(post.item, PostStatus.PROCESSING)]
    post.dynamo.client.transact_write_items(transacts)
    post.refresh_item()
    poster_path = post.get_poster_path()
    s3_uploads_client.put_object(poster_path, open(grant_path, 'rb'), 'image/jpeg')
    yield post


def test_cant_finish_processing_video_upload_various_errors(post_manager, user, pending_video_post):
    text_only_post = post_manager.add_post(user.id, 'pid-to', PostType.TEXT_ONLY, text='t')
    with pytest.raises(AssertionError, match='VIDEO'):
        text_only_post.finish_processing_video_upload()

    image_post = post_manager.add_post(user.id, 'pid-i', PostType.IMAGE, media_uploads=[{'mediaId': 'mid1'}])
    with pytest.raises(AssertionError, match='VIDEO'):
        image_post.finish_processing_video_upload()

    with pytest.raises(AssertionError, match='PROCESSING'):
        pending_video_post.finish_processing_video_upload()


def test_start_processing_video_upload_success(processing_video_post, s3_uploads_client):
    post = processing_video_post

    # check starting state
    assert post.item['postStatus'] == PostStatus.PROCESSING
    assert s3_uploads_client.exists(post.get_poster_path())
    assert not s3_uploads_client.exists(post.get_image_path(image_size.NATIVE))
    assert not s3_uploads_client.exists(post.get_image_path(image_size.K4))
    assert not s3_uploads_client.exists(post.get_image_path(image_size.P1080))
    assert not s3_uploads_client.exists(post.get_image_path(image_size.P480))
    assert not s3_uploads_client.exists(post.get_image_path(image_size.P64))

    # do the post processing
    post.finish_processing_video_upload()

    # check final state
    assert post.item['postStatus'] == PostStatus.COMPLETED
    assert not s3_uploads_client.exists(post.get_poster_path())
    assert s3_uploads_client.exists(post.get_image_path(image_size.NATIVE))
    assert s3_uploads_client.exists(post.get_image_path(image_size.K4))
    assert s3_uploads_client.exists(post.get_image_path(image_size.P1080))
    assert s3_uploads_client.exists(post.get_image_path(image_size.P480))
    assert s3_uploads_client.exists(post.get_image_path(image_size.P64))
