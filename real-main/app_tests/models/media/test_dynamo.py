import pendulum
import pytest

from app.models.post.enums import PostType
from app.models.media.dynamo import MediaDynamo


@pytest.fixture
def media_dynamo(dynamo_client):
    yield MediaDynamo(dynamo_client)


@pytest.fixture
def media_item(media_dynamo, post_manager):
    user_id = 'my-user-id'

    # add a post with media
    post = post_manager.add_post(user_id, 'pid', PostType.IMAGE)
    yield post.media.item


@pytest.fixture
def media_item_2(media_dynamo, post_manager):
    user_id = 'my-user-id-2'

    # add a post with media
    post = post_manager.add_post(user_id, 'pid-2', PostType.IMAGE)
    yield post.media.item


def test_media_does_not_exist(media_dynamo):
    media_id = 'my-post-id'
    resp = media_dynamo.get_media(media_id)
    assert resp is None


def test_media_exists(media_dynamo, post_manager):
    media_id = 'my-media-id'
    user_id = 'my-user-id'

    # add a post with media
    post_manager.add_post(user_id, 'pid', PostType.IMAGE, image_input={'mediaId': media_id})

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


def test_generate_by_post(media_dynamo, post_manager):
    user_id = 'uid'

    post_id_no_media = 'pid0'
    post_id_one_media = 'pid1'

    # add a post with one media
    post_manager.add_post(user_id, post_id_one_media, PostType.IMAGE, image_input={'mediaId': 'p1-mid'})

    # check post with no media
    medias = list(media_dynamo.generate_by_post(post_id_no_media))
    assert medias == []

    # check post with one media
    medias = list(media_dynamo.generate_by_post(post_id_one_media))
    assert [m['mediaId'] for m in medias] == ['p1-mid']


def test_transact_add_media_sans_options(media_dynamo):
    user_id = 'pbuid'
    post_id = 'pid'
    media_id = 'mid'

    # add the media
    before_str = pendulum.now('utc').to_iso8601_string()
    transacts = [media_dynamo.transact_add_media(user_id, post_id, media_id)]
    media_dynamo.client.transact_write_items(transacts)
    after_str = pendulum.now('utc').to_iso8601_string()

    # retrieve media, check format
    media_item = media_dynamo.get_media(media_id)
    posted_at_str = media_item['postedAt']
    assert before_str <= posted_at_str
    assert after_str >= posted_at_str
    assert media_item == {
        'schemaVersion': 2,
        'partitionKey': 'media/mid',
        'sortKey': '-',
        'gsiA1PartitionKey': 'media/pid',
        'gsiA1SortKey': '-',
        'userId': 'pbuid',
        'postId': 'pid',
        'postedAt': posted_at_str,
        'mediaId': 'mid',
        'mediaType': 'IMAGE',
    }


def test_transact_add_media_with_options(media_dynamo):
    user_id = 'pbuid'
    post_id = 'pid'
    media_id = 'mid'
    posted_at = pendulum.now('utc')

    # add the media
    transacts = [media_dynamo.transact_add_media(
        user_id, post_id, media_id, posted_at=posted_at, taken_in_real=True, original_format='oformat',
        image_format='HEIC'
    )]
    media_dynamo.client.transact_write_items(transacts)

    # retrieve media, check format
    posted_at_str = posted_at.to_iso8601_string()
    media_item = media_dynamo.get_media(media_id)
    assert media_item == {
        'schemaVersion': 2,
        'partitionKey': 'media/mid',
        'sortKey': '-',
        'gsiA1PartitionKey': 'media/pid',
        'gsiA1SortKey': '-',
        'userId': 'pbuid',
        'postId': 'pid',
        'postedAt': posted_at_str,
        'mediaId': 'mid',
        'mediaType': 'IMAGE',
        'takenInReal': True,
        'originalFormat': 'oformat',
        'imageFormat': 'HEIC',
    }


def test_transact_add_media_already_exists(media_dynamo):
    # add the media
    transacts = [media_dynamo.transact_add_media('pbuid', 'pid', 'mid')]
    media_dynamo.client.transact_write_items(transacts)

    # try to add it again
    with pytest.raises(media_dynamo.client.exceptions.ConditionalCheckFailedException):
        media_dynamo.client.transact_write_items(transacts)


def test_set_colors(media_dynamo, media_item):
    media_id = media_item['mediaId']
    assert 'colors' not in media_item

    # no support for deleting colors
    with pytest.raises(AssertionError):
        media_dynamo.set_colors(media_id, None)
    with pytest.raises(AssertionError):
        media_dynamo.set_colors(media_id, ())
    assert media_dynamo.get_media(media_id) == media_item

    # sample output from ColorTheif
    colors = [
        (52, 58, 46),
        (186, 206, 228),
        (144, 154, 170),
        (158, 180, 205),
        (131, 125, 125),
    ]

    new_media_item = media_dynamo.set_colors(media_id, colors)
    assert media_dynamo.get_media(media_id) == new_media_item
    assert new_media_item['colors'] == [
        {'r': 52, 'g': 58, 'b': 46},
        {'r': 186, 'g': 206, 'b': 228},
        {'r': 144, 'g': 154, 'b': 170},
        {'r': 158, 'g': 180, 'b': 205},
        {'r': 131, 'g': 125, 'b': 125},
    ]
    del new_media_item['colors']
    assert new_media_item == media_item
