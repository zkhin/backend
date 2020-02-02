from app.models.media.enums import MediaSize, MediaStatus

import pytest


@pytest.fixture
def media_awaiting_upload(media_manager, post_manager):
    media_uploads = [{'mediaId': 'mid', 'mediaType': media_manager.enums.MediaType.IMAGE}]
    post = post_manager.add_post('uid', 'pid', media_uploads=media_uploads)
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
    media_path = media.get_s3_path(MediaSize.NATIVE)
    media_manager.clients['s3_uploads'].put_object(media_path, content, 'application/octet-stream')

    # set the checksum, check what was saved to the DB
    media.set_checksum()
    assert media.item['checksum'] == md5
    media.refresh_item()
    assert media.item['checksum'] == md5
