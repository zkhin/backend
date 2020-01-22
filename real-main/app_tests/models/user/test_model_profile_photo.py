from unittest.mock import call

import pytest

from app.models.media import MediaManager
from app.models.media.enums import MediaSize
from app.models.post import PostManager
from app.models.post.dynamo import PostDynamo


@pytest.fixture
def user(user_manager):
    user_id = 'my-user-id'
    username = 'myUname'
    user = user_manager.create_cognito_only_user(user_id, username)
    yield user


@pytest.fixture
def post_manager(dynamo_client):
    yield PostManager({'dynamo': dynamo_client})


@pytest.fixture
def media_manager(dynamo_client):
    yield MediaManager({'dynamo': dynamo_client})


@pytest.fixture
def post_dynamo(dynamo_client):
    yield PostDynamo(dynamo_client)


@pytest.fixture
def uploaded_media(user, post_manager, post_dynamo, media_manager):
    post_id = 'post-id'
    media_id = 'media-id'
    photo_data = b'uploaded image'

    media_upload = {
        'mediaId': media_id,
        'mediaType': 'IMAGE',
    }

    post = post_manager.add_post(user.id, post_id, media_uploads=[media_upload])
    media = media_manager.init_media(post.item['mediaObjects'][0])
    for size in MediaSize._ALL:
        path = media.get_s3_path(size)
        user.s3_uploads_client.put_object(path, photo_data, 'application/octet-stream')
    media.set_status('UPLOADED')
    post_dynamo.client.transact_write_items([post_dynamo.transact_set_post_status(post.item, 'COMPLETED')])
    yield media


@pytest.fixture
def another_uploaded_media(user, post_manager, post_dynamo, media_manager):
    post_id = 'post-id-2'
    media_id = 'media-id-2'
    photo_data = b'another uploaded image'

    media_upload = {
        'mediaId': media_id,
        'mediaType': 'IMAGE',
    }

    post = post_manager.add_post(user.id, post_id, media_uploads=[media_upload])
    media = media_manager.init_media(post.item['mediaObjects'][0])
    for size in MediaSize._ALL:
        path = media.get_s3_path(size)
        user.s3_uploads_client.put_object(path, photo_data, 'application/octet-stream')
    media.set_status('UPLOADED')
    post_dynamo.client.transact_write_items([post_dynamo.transact_set_post_status(post.item, 'COMPLETED')])
    yield media


def test_get_photo_path(user, uploaded_media):
    # without photoMediaId set
    for size in MediaSize._ALL:
        assert user.get_photo_path(size) is None

    # set it
    user.update_photo(uploaded_media)
    assert user.item['photoMediaId'] == uploaded_media.id

    # should now return the paths
    for size in MediaSize._ALL:
        path = user.get_photo_path(size)
        assert path is not None
        assert size in path
        assert uploaded_media.id in path


def test_get_placeholder_photo_path(user, uploaded_media):
    user.placeholder_photos_directory = 'pp-photo-dir'

    # without placeholderPhotoCode set
    for size in MediaSize._ALL:
        assert user.get_placeholder_photo_path(size) is None

    # set it, just in memory but that's enough
    placeholder_photo_code = 'pp-code'
    user.item['placeholderPhotoCode'] = placeholder_photo_code

    # should now return the paths
    for size in MediaSize._ALL:
        path = user.get_placeholder_photo_path(size)
        assert path == f'{user.placeholder_photos_directory}/{placeholder_photo_code}/{size}.jpg'


def test_get_photo_url(user, uploaded_media, cloudfront_client):
    user.placeholder_photos_directory = 'pp-photo-dir'
    user.placeholder_photos_cloudfront_domain = 'pp-photo-domain'

    # neither set
    for size in MediaSize._ALL:
        assert user.get_photo_url(size) is None

    # placeholder code set
    placeholder_photo_code = 'pp-code'
    user.item['placeholderPhotoCode'] = placeholder_photo_code
    url_root = f'https://{user.placeholder_photos_cloudfront_domain}/{user.placeholder_photos_directory}'
    for size in MediaSize._ALL:
        url = user.get_photo_url(size)
        assert url == f'{url_root}/{placeholder_photo_code}/{size}.jpg'

    # photo media set
    user.update_photo(uploaded_media)
    assert user.item['photoMediaId'] == uploaded_media.id

    presigned_url = {}
    cloudfront_client.configure_mock(**{'generate_presigned_url.return_value': presigned_url})
    cloudfront_client.reset_mock()

    for size in MediaSize._ALL:
        url = user.get_photo_url(size)
        assert url is presigned_url
        path = user.get_photo_path(size)
        assert cloudfront_client.mock_calls == [call.generate_presigned_url(path, ['GET', 'HEAD'])]
        cloudfront_client.reset_mock()


def test_set_photo_first_time(user, uploaded_media):
    # verify it's not already set
    user.refresh_item()
    assert 'photoMediaId' not in user.item

    # set it
    user.update_photo(uploaded_media)
    assert user.item['photoMediaId'] == uploaded_media.id

    # verify it stuck in the db
    user.refresh_item()
    assert user.item['photoMediaId'] == uploaded_media.id

    # check it's in s3
    for size in MediaSize._ALL:
        path = user.get_photo_path(size)
        assert user.s3_uploads_client.exists(path)


def test_change_photo(user, uploaded_media, another_uploaded_media):
    # set it
    user.update_photo(uploaded_media)
    assert user.item['photoMediaId'] == uploaded_media.id

    # pull the original photo_data
    org_bodies = {}
    for size in MediaSize._ALL:
        path = user.get_photo_path(size)
        org_bodies[size] = list(user.s3_uploads_client.get_object_data_stream(path))

    # change it
    user.update_photo(another_uploaded_media)
    assert user.item['photoMediaId'] == another_uploaded_media.id

    # verify it stuck in the db
    user.refresh_item()
    assert user.item['photoMediaId'] == another_uploaded_media.id

    # pull the new photo_data
    for size in MediaSize._ALL:
        path = user.get_photo_path(size)
        new_body = list(user.s3_uploads_client.get_object_data_stream(path))
        assert new_body != org_bodies[size]

    # check the old photo data was deleted
    for size in MediaSize._ALL:
        path = user.get_photo_path(size, photo_media_id=uploaded_media.id)
        assert not user.s3_uploads_client.exists(path)


def test_delete_photo(user, uploaded_media):
    # set it
    user.update_photo(uploaded_media)
    assert user.item['photoMediaId'] == uploaded_media.id

    # delete it
    user.update_photo(None)
    assert 'photoMediaId' not in user.item

    # verify it stuck in the db
    user.refresh_item()
    assert 'photoMediaId' not in user.item

    # check s3 was cleared
    for size in MediaSize._ALL:
        path = user.get_photo_path(size, photo_media_id=uploaded_media.id)
        assert not user.s3_uploads_client.exists(path)
