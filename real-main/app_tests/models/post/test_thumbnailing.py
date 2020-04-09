from os import path

import pytest

from app.models.post.enums import PostStatus, PostType
from app.utils import image_size

grant_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'grant.jpg')
squirrel_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'squirrel.png')


@pytest.fixture
def pending_post(post_manager):
    yield post_manager.add_post('uid', 'pid', PostType.IMAGE)


def test_is_native_image_jpeg_success(s3_uploads_client, pending_post):
    # put a jpeg image in the bucket
    path = pending_post.get_image_path(image_size.NATIVE)
    s3_uploads_client.put_object(path, open(grant_path, 'rb'), 'image/jpeg')
    pending_post.item['postStatus'] = PostStatus.COMPLETED

    assert pending_post.is_native_image_jpeg()


def test_is_native_image_jpeg_failure(s3_uploads_client, pending_post):
    # put a png image in the bucket
    path = pending_post.get_image_path(image_size.NATIVE)
    s3_uploads_client.put_object(path, open(squirrel_path, 'rb'), 'image/png')
    pending_post.item['postStatus'] = PostStatus.COMPLETED

    assert pending_post.is_native_image_jpeg() is False


def test_is_native_image_jpeg_failure_with_exception(s3_uploads_client, pending_post):
    # put garbage in the bucket
    path = pending_post.get_image_path(image_size.NATIVE)
    s3_uploads_client.put_object(path, b'not an image', 'application/octet-stream')
    pending_post.item['postStatus'] = PostStatus.COMPLETED

    assert pending_post.is_native_image_jpeg() is False
