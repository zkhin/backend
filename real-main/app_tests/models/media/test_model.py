from os import path
from unittest.mock import Mock, call

from PIL import Image
import pytest

from app.models.media.enums import MediaStatus
from app.models.post.enums import PostType
from app.utils import image_size


heic_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'IMG_0265.HEIC')
heic_width = 4032
heic_height = 3024


@pytest.fixture
def post(post_manager):
    yield post_manager.add_post('uid', 'pid', PostType.IMAGE)


@pytest.fixture
def media_awaiting_upload(media_manager, post):
    media_item = post.item['mediaObjects'][0]
    yield media_manager.init_media(media_item)


@pytest.fixture
def media_awaiting_upload_heic(post_manager, media_manager):
    post = post_manager.add_post('uid', 'pid2', PostType.IMAGE, image_input={'imageFormat': 'HEIC'})
    media_item = post.item['mediaObjects'][0]
    yield media_manager.init_media(media_item)


def test_refresh_item(dynamo_client, media_awaiting_upload):
    media = media_awaiting_upload

    # change something behind the models back, directly in dynamo
    field = 'doesnotexist'
    value = 'yes'
    resp = dynamo_client.update_item({
        'Key': {
            'partitionKey': media.item['partitionKey'],
            'sortKey': media.item['sortKey'],
        },
        'UpdateExpression': 'SET #f = :v',
        'ExpressionAttributeValues': {':v': value},
        'ExpressionAttributeNames': {'#f': field},
    })
    assert resp[field] == value
    assert field not in media.item

    media.refresh_item()
    assert media.item[field] == value


def test_process_upload_wrong_status(media_awaiting_upload):
    media_awaiting_upload.item['mediaStatus'] = MediaStatus.UPLOADED
    with pytest.raises(AssertionError, match='status'):
        media_awaiting_upload.process_upload()

    media_awaiting_upload.item['mediaStatus'] = MediaStatus.ARCHIVED
    with pytest.raises(AssertionError, match='status'):
        media_awaiting_upload.process_upload()

    media_awaiting_upload.item['mediaStatus'] = MediaStatus.DELETING
    with pytest.raises(AssertionError, match='status'):
        media_awaiting_upload.process_upload()


def test_process_upload_success(media_awaiting_upload):
    media = media_awaiting_upload
    assert media.item['mediaStatus'] == MediaStatus.AWAITING_UPLOAD

    # mock out a bunch of methods
    media.set_native_jpeg = Mock()
    media.set_is_verified = Mock()
    media.set_height_and_width = Mock()
    media.set_colors = Mock()
    media.set_thumbnails = Mock()

    # do the call, should update our status
    media.process_upload()
    assert media.item['mediaStatus'] == MediaStatus.UPLOADED

    # check the mocks were called correctly
    assert media.set_is_verified.mock_calls == [call()]
    assert media.set_height_and_width.mock_calls == [call()]
    assert media.set_colors.mock_calls == [call()]
    assert media.set_thumbnails.mock_calls == [call()]


def test_process_upload_success_heic(media_awaiting_upload_heic):
    media = media_awaiting_upload_heic
    assert media.item['mediaStatus'] == MediaStatus.AWAITING_UPLOAD

    # mock out a bunch of methods
    media.set_native_jpeg = Mock()
    media.set_is_verified = Mock()
    media.set_height_and_width = Mock()
    media.set_colors = Mock()
    media.set_thumbnails = Mock()

    # do the call, should update our status
    media.process_upload()
    assert media.item['mediaStatus'] == MediaStatus.UPLOADED

    # check the mocks were called correctly
    assert media.set_is_verified.mock_calls == [call()]
    assert media.set_height_and_width.mock_calls == [call()]
    assert media.set_colors.mock_calls == [call()]
    assert media.set_thumbnails.mock_calls == [call()]


def test_set_status(media_awaiting_upload):
    assert media_awaiting_upload.item['mediaStatus'] == MediaStatus.AWAITING_UPLOAD

    media_awaiting_upload.set_status(MediaStatus.ERROR)
    assert media_awaiting_upload.item['mediaStatus'] == MediaStatus.ERROR

    media_awaiting_upload.refresh_item()
    assert media_awaiting_upload.item['mediaStatus'] == MediaStatus.ERROR


def test_set_is_verified_minimal(media_awaiting_upload, post):
    # check initial state and configure mock
    media = media_awaiting_upload
    assert 'isVerified' not in media.item
    media.post_verification_client = Mock(**{'verify_image.return_value': False})

    # do the call, check final state
    media.set_is_verified()
    assert media.item['isVerified'] is False
    media.refresh_item()
    assert media.item['isVerified'] is False

    # check mock called correctly
    assert media.post_verification_client.mock_calls == [
        call.verify_image(post.get_image_readonly_url(image_size.NATIVE), taken_in_real=None, original_format=None),
    ]


def test_set_is_verified_maximal(media_awaiting_upload, post):
    # check initial state and configure mock
    media = media_awaiting_upload
    assert 'isVerified' not in media.item
    media.post_verification_client = Mock(**{'verify_image.return_value': True})
    media.item['takenInReal'] = False
    media.item['originalFormat'] = 'oo'

    # do the call, check final state
    media.set_is_verified()
    assert media.item['isVerified'] is True
    media.refresh_item()
    assert media.item['isVerified'] is True

    # check mock called correctly
    assert media.post_verification_client.mock_calls == [
        call.verify_image(post.get_image_readonly_url(image_size.NATIVE), taken_in_real=False, original_format='oo'),
    ]


def test_set_native_jpeg(media_awaiting_upload, s3_uploads_client):
    media = media_awaiting_upload

    # put the heic image in the bucket
    s3_heic_path = media.get_s3_path(image_size.NATIVE_HEIC)
    s3_uploads_client.put_object(s3_heic_path, open(heic_path, 'rb'), 'image/heic')

    # verify there's no native jpeg
    s3_jpeg_path = media.get_s3_path(image_size.NATIVE)
    assert not s3_uploads_client.exists(s3_jpeg_path)

    media.set_native_jpeg()

    # verify there is now a native jpeg, of the correct size
    image = Image.open(media.get_native_image_buffer())
    assert image.size == (heic_width, heic_height)
