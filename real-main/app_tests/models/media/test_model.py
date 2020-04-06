import base64
from unittest.mock import Mock, call

import pytest

from app.models.media.enums import MediaStatus
from app.models.post.enums import PostType
from app.utils import image_size


@pytest.fixture
def media_awaiting_upload(media_manager, post_manager):
    post = post_manager.add_post('uid', 'pid', PostType.IMAGE)
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


def test_process_upload_failure_non_jpeg(media_awaiting_upload):
    media = media_awaiting_upload
    assert media.item['mediaStatus'] == MediaStatus.AWAITING_UPLOAD

    # mock out a bunch of methods
    media.is_original_jpeg = Mock(return_value=False)
    media.set_is_verified = Mock()
    media.set_height_and_width = Mock()
    media.set_colors = Mock()
    media.set_thumbnails = Mock()
    media.set_checksum = Mock()

    # do the call, should update our status
    with pytest.raises(media.exceptions.MediaException, match='Non-jpeg'):
        media.process_upload()
    assert media.item['mediaStatus'] == MediaStatus.PROCESSING_UPLOAD

    # check the mocks were not called
    assert media.set_is_verified.mock_calls == []
    assert media.set_height_and_width.mock_calls == []
    assert media.set_colors.mock_calls == []
    assert media.set_thumbnails.mock_calls == []
    assert media.set_checksum.mock_calls == []


def test_process_upload_success(media_awaiting_upload):
    media = media_awaiting_upload
    assert media.item['mediaStatus'] == MediaStatus.AWAITING_UPLOAD

    # mock out a bunch of methods
    media.is_original_jpeg = Mock(return_value=True)
    media.set_is_verified = Mock()
    media.set_height_and_width = Mock()
    media.set_colors = Mock()
    media.set_thumbnails = Mock()
    media.set_checksum = Mock()

    # do the call, should update our status
    media.process_upload()
    assert media.item['mediaStatus'] == MediaStatus.UPLOADED

    # check the mocks were called correctly
    assert media.set_is_verified.mock_calls == [call()]
    assert media.set_height_and_width.mock_calls == [call()]
    assert media.set_colors.mock_calls == [call()]
    assert media.set_thumbnails.mock_calls == [call()]
    assert media.set_checksum.mock_calls == [call()]


def test_upload_native_image_data_base64(media_awaiting_upload):
    media = media_awaiting_upload
    native_path = media.get_s3_path(image_size.NATIVE)
    image_data = b'imagedatahere'
    image_data_b64 = base64.b64encode(image_data)

    # check no data on media, nor in s3
    assert not hasattr(media, '_native_image_data')
    with pytest.raises(media.s3_uploads_client.exceptions.NoSuchKey):
        assert media.s3_uploads_client.get_object_data_stream(native_path)

    # put data up there
    media.upload_native_image_data_base64(image_data_b64)

    # check it was placed in mem and in s3
    assert media.get_native_image_buffer().read() == image_data
    assert media.s3_uploads_client.get_object_data_stream(native_path).read() == image_data


def test_set_status(media_awaiting_upload):
    assert media_awaiting_upload.item['mediaStatus'] == MediaStatus.AWAITING_UPLOAD

    media_awaiting_upload.set_status(MediaStatus.ERROR)
    assert media_awaiting_upload.item['mediaStatus'] == MediaStatus.ERROR

    media_awaiting_upload.refresh_item()
    assert media_awaiting_upload.item['mediaStatus'] == MediaStatus.ERROR


def test_set_checksum(media_manager, media_awaiting_upload):
    media = media_awaiting_upload
    assert 'checksum' not in media.item

    # put some content with a known md5 up in s3
    content = b'anything'
    md5 = 'f0e166dc34d14d6c228ffac576c9a43c'
    media_path = media.get_s3_path(image_size.NATIVE)
    media_manager.clients['s3_uploads'].put_object(media_path, content, 'application/octet-stream')

    # set the checksum, check what was saved to the DB
    media.set_checksum()
    assert media.item['checksum'] == md5
    media.refresh_item()
    assert media.item['checksum'] == md5


def test_set_is_verified_minimal(media_awaiting_upload):
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
        call.verify_image(media.get_readonly_url(image_size.NATIVE), taken_in_real=None, original_format=None),
    ]


def test_set_is_verified_maximal(media_awaiting_upload):
    # check initial state and configure mock
    media = media_awaiting_upload
    assert 'isVerified' not in media.item
    media.post_verification_client = Mock(**{'verify_image.return_value': True})
    media.item['takenInReal'] = False
    media.item['originalFormat'] = 'oreo'

    # do the call, check final state
    media.set_is_verified()
    assert media.item['isVerified'] is True
    media.refresh_item()
    assert media.item['isVerified'] is True

    # check mock called correctly
    assert media.post_verification_client.mock_calls == [
        call.verify_image(media.get_readonly_url(image_size.NATIVE), taken_in_real=False, original_format='oreo'),
    ]
