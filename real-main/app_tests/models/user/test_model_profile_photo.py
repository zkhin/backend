import base64
from os import path
from unittest.mock import call

import pytest

from app.models.post.enums import PostType
from app.utils import image_size

grant_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'grant.jpg')


@pytest.fixture
def grant_data_b64():
    with open(grant_path, 'rb') as fh:
        yield base64.b64encode(fh.read())


@pytest.fixture
def user(user_manager):
    user_id = 'my-user-id'
    username = 'myUname'
    user = user_manager.create_cognito_only_user(user_id, username)
    yield user


@pytest.fixture
def uploaded_post(user, post_manager, image_data_b64, mock_post_verification_api):
    post_id = 'post-id'
    media_uploads = [{'mediaId': 'media-id', 'imageData': image_data_b64}]
    yield post_manager.add_post(user.id, post_id, PostType.IMAGE, media_uploads=media_uploads)


@pytest.fixture
def another_uploaded_post(user, post_manager, grant_data_b64, mock_post_verification_api):
    post_id = 'post-id-2'
    media_uploads = [{'mediaId': 'media-id-2', 'imageData': grant_data_b64}]
    yield post_manager.add_post(user.id, post_id, PostType.IMAGE, media_uploads=media_uploads)


def test_get_photo_path(user, uploaded_post):
    # without photoPostId set
    for size in image_size.ALL:
        assert user.get_photo_path(size) is None

    # set it
    user.update_photo(uploaded_post)
    assert user.item['photoPostId'] == uploaded_post.id

    # should now return the paths
    for size in image_size.ALL:
        path = user.get_photo_path(size)
        assert path is not None
        assert size.name in path
        assert uploaded_post.id in path


def test_get_placeholder_photo_path(user):
    user.placeholder_photos_directory = 'pp-photo-dir'

    # without placeholderPhotoCode set
    for size in image_size.ALL:
        assert user.get_placeholder_photo_path(size) is None

    # set it, just in memory but that's enough
    placeholder_photo_code = 'pp-code'
    user.item['placeholderPhotoCode'] = placeholder_photo_code

    # should now return the paths
    for size in image_size.ALL:
        path = user.get_placeholder_photo_path(size)
        assert path == f'{user.placeholder_photos_directory}/{placeholder_photo_code}/{size.name}.jpg'


def test_get_photo_url(user, uploaded_post, cloudfront_client):
    user.placeholder_photos_directory = 'pp-photo-dir'
    user.frontend_resources_domain = 'pp-photo-domain'

    # neither set
    for size in image_size.ALL:
        assert user.get_photo_url(size) is None

    # placeholder code set
    placeholder_photo_code = 'pp-code'
    user.item['placeholderPhotoCode'] = placeholder_photo_code
    url_root = f'https://{user.frontend_resources_domain}/{user.placeholder_photos_directory}'
    for size in image_size.ALL:
        url = user.get_photo_url(size)
        assert url == f'{url_root}/{placeholder_photo_code}/{size.name}.jpg'

    # photo post set
    user.update_photo(uploaded_post)
    assert user.item['photoPostId'] == uploaded_post.id

    presigned_url = {}
    cloudfront_client.configure_mock(**{'generate_presigned_url.return_value': presigned_url})
    cloudfront_client.reset_mock()

    for size in image_size.ALL:
        url = user.get_photo_url(size)
        assert url is presigned_url
        path = user.get_photo_path(size)
        assert cloudfront_client.mock_calls == [call.generate_presigned_url(path, ['GET', 'HEAD'])]
        cloudfront_client.reset_mock()


def test_set_photo_multiple_times(user, uploaded_post, another_uploaded_post):
    # verify it's not already set
    user.refresh_item()
    assert 'photoPostId' not in user.item

    # set it
    user.update_photo(uploaded_post)
    assert user.item['photoPostId'] == uploaded_post.id

    # verify it stuck in the db
    user.refresh_item()
    assert user.item['photoPostId'] == uploaded_post.id

    # check it's in s3
    for size in image_size.ALL:
        path = user.get_photo_path(size)
        assert user.s3_uploads_client.exists(path)

    # pull the photo_data we just set up there
    org_bodies = {}
    for size in image_size.ALL:
        path = user.get_photo_path(size)
        org_bodies[size] = list(user.s3_uploads_client.get_object_data_stream(path))

    # change it
    user.update_photo(another_uploaded_post)
    assert user.item['photoPostId'] == another_uploaded_post.id

    # verify it stuck in the db
    user.refresh_item()
    assert user.item['photoPostId'] == another_uploaded_post.id

    # pull the new photo_data
    for size in image_size.ALL:
        path = user.get_photo_path(size)
        new_body = list(user.s3_uploads_client.get_object_data_stream(path))
        assert new_body != org_bodies[size]

    # verify the old images are still there
    # we don't delete them as there may still be un-expired signed urls pointing to the old images
    for size in image_size.ALL:
        path = user.get_photo_path(size, photo_post_id=uploaded_post.id)
        assert user.s3_uploads_client.exists(path)


def test_clear_photo_s3_objects(user, uploaded_post, another_uploaded_post):
    # set it
    user.update_photo(uploaded_post)
    assert user.item['photoPostId'] == uploaded_post.id

    # change it
    user.update_photo(another_uploaded_post)
    assert user.item['photoPostId'] == another_uploaded_post.id

    # verify a bunch of stuff is in S3 now, old and new
    for size in image_size.ALL:
        old_path = user.get_photo_path(size, photo_post_id=uploaded_post.id)
        new_path = user.get_photo_path(size, photo_post_id=another_uploaded_post.id)
        assert user.s3_uploads_client.exists(old_path)
        assert user.s3_uploads_client.exists(new_path)

    # clear it all away
    user.clear_photo_s3_objects()

    # verify all profile photos, old and new, were deleted from s3
    for size in image_size.ALL:
        old_path = user.get_photo_path(size, photo_post_id=uploaded_post.id)
        new_path = user.get_photo_path(size, photo_post_id=another_uploaded_post.id)
        assert not user.s3_uploads_client.exists(old_path)
        assert not user.s3_uploads_client.exists(new_path)
