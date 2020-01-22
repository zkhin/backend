from datetime import datetime

import pytest

from app.models.media.dynamo import MediaDynamo
from app.models.media.enums import MediaStatus, MediaType


@pytest.fixture
def media_dynamo(dynamo_client):
    yield MediaDynamo(dynamo_client)


@pytest.fixture
def media_item(media_dynamo, post_manager):
    media_id = 'my-media-id'
    user_id = 'my-user-id'

    # add a post with media
    media_uploads = [{'mediaId': media_id, 'mediaType': 'IMAGE'}]
    post = post_manager.add_post(user_id, 'pid', media_uploads=media_uploads)
    yield post.item['mediaObjects'][0]


def test_media_does_not_exist(media_dynamo):
    media_id = 'my-post-id'
    resp = media_dynamo.get_media(media_id)
    assert resp is None


def test_media_exists(media_dynamo, post_manager):
    media_id = 'my-media-id'
    user_id = 'my-user-id'

    # add a post with media
    media_uploads = [{'mediaId': media_id, 'mediaType': 'IMAGE'}]
    post_manager.add_post(user_id, 'pid', media_uploads=media_uploads)

    # media exists now
    resp = media_dynamo.get_media(media_id)
    assert resp['mediaId'] == media_id

    # check strongly_consistent kwarg accepted
    resp = media_dynamo.get_media(media_id, strongly_consistent=True)
    assert resp['mediaId'] == media_id


def test_media_set_is_verified(media_dynamo, media_item):
    media_id = media_item['mediaId']
    assert 'isVerified' not in media_item

    media_item = media_dynamo.set_is_verified(media_id, True)
    assert media_item['isVerified'] is True

    media_item = media_dynamo.set_is_verified(media_id, False)
    assert media_item['isVerified'] is False


def test_media_set_height_and_width(media_dynamo, media_item):
    media_id = media_item['mediaId']
    assert 'height' not in media_item
    assert 'width' not in media_item

    media_item = media_dynamo.set_height_and_width(media_id, 4, 2)
    assert media_item['height'] == 4
    assert media_item['width'] == 2

    media_item = media_dynamo.set_height_and_width(media_id, 120, 2000)
    assert media_item['height'] == 120
    assert media_item['width'] == 2000


def test_media_set_status(media_dynamo, media_item):
    assert media_item['mediaStatus'] == MediaStatus.AWAITING_UPLOAD

    transact = media_dynamo.transact_set_status(media_item, MediaStatus.UPLOADED)
    media_dynamo.client.transact_write_items([transact])
    assert media_dynamo.get_media(media_item['mediaId'])['mediaStatus'] == MediaStatus.UPLOADED

    transact = media_dynamo.transact_set_status(media_item, MediaStatus.ERROR)
    media_dynamo.client.transact_write_items([transact])
    assert media_dynamo.get_media(media_item['mediaId'])['mediaStatus'] == MediaStatus.ERROR


def test_generate_by_user(media_dynamo, post_manager):
    user_id = 'uid'

    # with no media
    medias = list(media_dynamo.generate_by_user(user_id))
    assert medias == []

    # add a post with media
    media_uploads = [{'mediaId': 'mid', 'mediaType': 'IMAGE'}]
    post_manager.add_post(user_id, 'pid', media_uploads=media_uploads)

    # list media again, check correct
    medias = list(media_dynamo.generate_by_user(user_id))
    assert [m['mediaId'] for m in medias] == ['mid']

    # add another post with media
    media_uploads = [{'mediaId': 'mid2', 'mediaType': 'IMAGE'}]
    post_manager.add_post(user_id, 'pid2', media_uploads=media_uploads)

    # list media again, check correct
    medias = list(media_dynamo.generate_by_user(user_id))
    assert [m['mediaId'] for m in medias] == ['mid', 'mid2']

    # now a different user adds a post with
    media_uploads = [{'mediaId': 'mid3', 'mediaType': 'IMAGE'}]
    post_manager.add_post('otherid', 'pid3', media_uploads=media_uploads)

    # list media again, check hasn't changed
    medias = list(media_dynamo.generate_by_user(user_id))
    assert [m['mediaId'] for m in medias] == ['mid', 'mid2']


def test_generate_by_post(media_dynamo, post_manager):
    user_id = 'uid'

    post_id_no_media = 'pid0'
    post_id_one_media = 'pid1'
    post_id_two_media = 'pid2'

    # add a post with one media
    media_uploads = [{'mediaId': 'p1-mid', 'mediaType': 'IMAGE'}]
    post_manager.add_post(user_id, post_id_one_media, media_uploads=media_uploads)

    # add a post with two media
    media_uploads = [
        {'mediaId': 'p2-mid1', 'mediaType': 'IMAGE'},
        {'mediaId': 'p2-mid2', 'mediaType': 'IMAGE'},
    ]
    post_manager.add_post(user_id, post_id_two_media, media_uploads=media_uploads)

    # check post with no media
    medias = list(media_dynamo.generate_by_post(post_id_no_media))
    assert medias == []

    # check post with one media
    medias = list(media_dynamo.generate_by_post(post_id_one_media))
    assert [m['mediaId'] for m in medias] == ['p1-mid']

    # check post with two medias
    medias = list(media_dynamo.generate_by_post(post_id_two_media))
    assert [m['mediaId'] for m in medias] == ['p2-mid1', 'p2-mid2']


def test_generate_by_post_uploaded_or_not(media_dynamo, post_manager):
    # add a post with two media
    media_uploads = [
        {'mediaId': 'mid1', 'mediaType': 'IMAGE'},
        {'mediaId': 'mid2', 'mediaType': 'IMAGE'},
    ]
    post_manager.add_post('uid', 'pid', media_uploads=media_uploads)

    # check generation
    media_items = list(media_dynamo.generate_by_post('pid'))
    assert len(media_items) == 2
    assert len(list(media_dynamo.generate_by_post('pid', uploaded=False))) == 2
    assert len(list(media_dynamo.generate_by_post('pid', uploaded=True))) == 0

    # mark one media uploaded
    transact = media_dynamo.transact_set_status(media_items[0], MediaStatus.UPLOADED)
    media_dynamo.client.transact_write_items([transact])

    # check generation
    assert len(list(media_dynamo.generate_by_post('pid'))) == 2
    assert len(list(media_dynamo.generate_by_post('pid', uploaded=False))) == 1
    assert len(list(media_dynamo.generate_by_post('pid', uploaded=True))) == 1

    # mark the other media uploaded
    transact = media_dynamo.transact_set_status(media_items[1], MediaStatus.UPLOADED)
    media_dynamo.client.transact_write_items([transact])

    # check generation
    assert len(list(media_dynamo.generate_by_post('pid'))) == 2
    assert len(list(media_dynamo.generate_by_post('pid', uploaded=False))) == 0
    assert len(list(media_dynamo.generate_by_post('pid', uploaded=True))) == 2


def test_transact_add_media_sans_options(media_dynamo):
    user_id = 'pbuid'
    post_id = 'pid'
    media_id = 'mid'
    media_type = 'mtype'
    posted_at = datetime.utcnow()

    # add the media
    transacts = [media_dynamo.transact_add_media(user_id, post_id, media_id, media_type, posted_at=posted_at)]
    media_dynamo.client.transact_write_items(transacts)

    # retrieve media, check format
    posted_at_str = posted_at.isoformat() + 'Z'
    media_item = media_dynamo.get_media(media_id)
    assert media_item == {
        'schemaVersion': 0,
        'partitionKey': 'media/mid',
        'sortKey': '-',
        'gsiA1PartitionKey': 'media/pid',
        'gsiA1SortKey': MediaStatus.AWAITING_UPLOAD,
        'gsiA2PartitionKey': 'media/pbuid',
        'gsiA2SortKey': 'mtype/' + MediaStatus.AWAITING_UPLOAD + '/' + posted_at_str,
        'userId': 'pbuid',
        'postId': 'pid',
        'postedAt': posted_at_str,
        'mediaId': 'mid',
        'mediaType': 'mtype',
        'mediaStatus': MediaStatus.AWAITING_UPLOAD,
    }


def test_transact_add_media_with_options(media_dynamo):
    user_id = 'pbuid'
    post_id = 'pid'
    media_id = 'mid'
    media_type = 'mtype'
    posted_at = datetime.utcnow()

    # add the media
    transacts = [media_dynamo.transact_add_media(
        user_id, post_id, media_id, media_type, posted_at=posted_at, taken_in_real=True,
        original_format='oformat'
    )]
    media_dynamo.client.transact_write_items(transacts)

    # retrieve media, check format
    posted_at_str = posted_at.isoformat() + 'Z'
    media_item = media_dynamo.get_media(media_id)
    assert media_item == {
        'schemaVersion': 0,
        'partitionKey': 'media/mid',
        'sortKey': '-',
        'gsiA1PartitionKey': 'media/pid',
        'gsiA1SortKey': MediaStatus.AWAITING_UPLOAD,
        'gsiA2PartitionKey': 'media/pbuid',
        'gsiA2SortKey': 'mtype/' + MediaStatus.AWAITING_UPLOAD + '/' + posted_at_str,
        'userId': 'pbuid',
        'postId': 'pid',
        'postedAt': posted_at_str,
        'mediaId': 'mid',
        'mediaType': 'mtype',
        'mediaStatus': MediaStatus.AWAITING_UPLOAD,
        'takenInReal': True,
        'originalFormat': 'oformat',
    }


def test_transact_add_media_already_exists(media_dynamo):
    # add the media
    transacts = [media_dynamo.transact_add_media('pbuid', 'pid', 'mid', MediaType.IMAGE)]
    media_dynamo.client.transact_write_items(transacts)

    # try to add it again
    with pytest.raises(media_dynamo.client.exceptions.ConditionalCheckFailedException):
        media_dynamo.client.transact_write_items(transacts)
