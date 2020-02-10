from unittest.mock import call

from app.models.media import MediaManager
from app.models.media.model import Media
from app.models.media.enums import MediaType, MediaSize, MediaStatus


def test_get_s3_path():
    item = {
        'userId': 'us-east-1:user-id',
        'postId': 'post-id',
        'mediaId': 'media-id',
        'mediaType': MediaType.IMAGE,
    }

    media = Media(item, None)
    path = media.get_s3_path(MediaSize.NATIVE)
    assert path == 'us-east-1:user-id/post/post-id/media/media-id/native.jpg'


def test_parse_post_media_path():
    path = 'us-east-1:user-id/post/post-id/media/media-id/native.jpg'
    user_id, post_id, media_id, media_size, media_ext = MediaManager({}).parse_s3_path(path)
    assert user_id == 'us-east-1:user-id'
    assert post_id == 'post-id'
    assert media_id == 'media-id'
    assert media_size == 'native'
    assert media_ext == 'jpg'


def test_get_readonly_url(cloudfront_client):
    item = {
        'userId': 'user-id',
        'postId': 'post-id',
        'mediaId': 'media-id',
        'mediaType': MediaType.IMAGE,
    }
    expected_url = {}
    cloudfront_client.configure_mock(**{
        'generate_presigned_url.return_value': expected_url,
    })

    media = Media(item, None, cloudfront_client=cloudfront_client)
    url = media.get_readonly_url(MediaSize.NATIVE)
    assert url == expected_url

    expected_path = 'user-id/post/post-id/media/media-id/native.jpg'
    assert cloudfront_client.mock_calls == [call.generate_presigned_url(expected_path, ['GET', 'HEAD'])]


def test_get_readonly_url_not_uploaded():
    source = {'mediaId': 'mid', 'path': 'path', 'mediaStatus': MediaStatus.AWAITING_UPLOAD}
    media = Media(source, None)
    url = media.get_readonly_url('really-big')
    assert url is None


def test_get_writeonly_url(cloudfront_client):
    item = {
        'userId': 'user-id',
        'postId': 'post-id',
        'mediaId': 'media-id',
        'mediaType': MediaType.IMAGE,
        'mediaStatus': MediaStatus.AWAITING_UPLOAD,
    }
    expected_url = {}
    cloudfront_client.configure_mock(**{
        'generate_presigned_url.return_value': expected_url,
    })

    media = Media(item, None, cloudfront_client=cloudfront_client)
    url = media.get_writeonly_url()
    assert url == expected_url

    expected_path = 'user-id/post/post-id/media/media-id/native.jpg'
    assert cloudfront_client.mock_calls == [call.generate_presigned_url(expected_path, ['PUT'])]


def test_get_writeonly_url_already_uploaded():
    source = {'mediaId': 'mid', 'path': 'path', 'mediaStatus': MediaStatus.UPLOADED}
    media = Media(source, None)
    url = media.get_writeonly_url()
    assert url is None


def test_image_has_all_s3_objects(s3_client):
    # media with no s3 objects
    media_item = {
        'userId': 'uid',
        'postId': 'pid',
        'mediaId': 'mid',
        'mediaType': MediaType.IMAGE
    }
    media = Media(media_item, None, s3_uploads_client=s3_client)
    assert media.has_all_s3_objects() is False

    # media with just native resolution
    path = media.get_s3_path(MediaSize.NATIVE)
    media.s3_uploads_client.put_object(path, b'data', 'application/octet-stream')
    assert media.has_all_s3_objects() is False

    # media with all sizes resolution
    path = media.get_s3_path(MediaSize.P64)
    media.s3_uploads_client.put_object(path, b'data', 'application/octet-stream')
    path = media.get_s3_path(MediaSize.P480)
    media.s3_uploads_client.put_object(path, b'data', 'application/octet-stream')
    path = media.get_s3_path(MediaSize.P1080)
    media.s3_uploads_client.put_object(path, b'data', 'application/octet-stream')
    path = media.get_s3_path(MediaSize.K4)
    media.s3_uploads_client.put_object(path, b'data', 'application/octet-stream')
    assert media.has_all_s3_objects() is True


def test_video_has_all_s3_objects(s3_client):
    # video with no s3 objects
    media_item = {
        'userId': 'uid',
        'postId': 'pid',
        'mediaId': 'mid',
        'mediaType': MediaType.VIDEO
    }
    media = Media(media_item, None, s3_uploads_client=s3_client)
    assert media.has_all_s3_objects() is False

    # video with just native resolution
    path = media.get_s3_path(MediaSize.NATIVE)
    media.s3_uploads_client.put_object(path, b'data', 'application/octet-stream')
    assert media.has_all_s3_objects() is True


def test_delete_all_s3_objects(s3_client):
    media_item = {
        'userId': 'uid',
        'postId': 'pid',
        'mediaId': 'mid',
        'mediaType': MediaType.IMAGE
    }
    media = Media(media_item, None, s3_uploads_client=s3_client)

    # upload native and the three thumbnails
    path = media.get_s3_path(MediaSize.NATIVE)
    media.s3_uploads_client.put_object(path, b'data', 'application/octet-stream')
    path = media.get_s3_path(MediaSize.P64)
    media.s3_uploads_client.put_object(path, b'data', 'application/octet-stream')
    path = media.get_s3_path(MediaSize.P480)
    media.s3_uploads_client.put_object(path, b'data', 'application/octet-stream')
    path = media.get_s3_path(MediaSize.P1080)
    media.s3_uploads_client.put_object(path, b'data', 'application/octet-stream')
    path = media.get_s3_path(MediaSize.K4)
    media.s3_uploads_client.put_object(path, b'data', 'application/octet-stream')
    assert media.has_all_s3_objects() is True

    # should not error out
    media.delete_all_s3_objects()
    assert media.has_all_s3_objects() is False


def test_delete_all_s3_objects_no_objects(s3_client):
    media_item = {
        'userId': 'uid',
        'postId': 'pid',
        'mediaId': 'mid',
        'mediaType': MediaType.IMAGE
    }
    media = Media(media_item, None, s3_uploads_client=s3_client)
    assert media.has_all_s3_objects() is False

    # should not error out
    media.delete_all_s3_objects()

    assert media.has_all_s3_objects() is False
