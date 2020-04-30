import pendulum
import pytest

from app.models.post.dynamo import PostImageDynamo


@pytest.fixture
def post_image_dynamo(dynamo_client):
    yield PostImageDynamo(dynamo_client)


@pytest.fixture
def image_item(post_image_dynamo):
    transact = post_image_dynamo.transact_add('uid', 'pid', 'mid')
    post_image_dynamo.client.transact_write_items([transact])
    yield next(post_image_dynamo.generate_by_post('pid'), None)


def test_transact_add_minimal(post_image_dynamo):
    # add the post iamge
    before = pendulum.now()
    transact = post_image_dynamo.transact_add('uid1', 'pid1', 'mid1')
    after = pendulum.now()
    post_image_dynamo.client.transact_write_items([transact])

    # check format
    item = post_image_dynamo.get('mid1')
    assert item.pop('schemaVersion') == 2
    assert item.pop('partitionKey') == 'media/mid1'
    assert item.pop('sortKey') == '-'
    assert item.pop('gsiA1PartitionKey') == 'media/pid1'
    assert item.pop('gsiA1SortKey') == '-'
    assert item.pop('userId') == 'uid1'
    assert item.pop('postId') == 'pid1'
    assert item.pop('mediaId') == 'mid1'
    assert item.pop('mediaType') == 'IMAGE'
    posted_at = pendulum.parse(item.pop('postedAt'))
    assert posted_at > before
    assert posted_at < after
    assert item == {}

    # verify we can't add it again
    with pytest.raises(post_image_dynamo.client.exceptions.ConditionalCheckFailedException):
        post_image_dynamo.client.transact_write_items([transact])


def test_transact_add_maximal(post_image_dynamo):
    # add the post iamge
    posted_at = pendulum.now()
    transact = post_image_dynamo.transact_add('uid2', 'pid2', 'mid2', posted_at=posted_at, taken_in_real=True,
                                              original_format='of', image_format='if')
    post_image_dynamo.client.transact_write_items([transact])

    # check format
    item = post_image_dynamo.get('mid2')
    assert item.pop('schemaVersion') == 2
    assert item.pop('partitionKey') == 'media/mid2'
    assert item.pop('sortKey') == '-'
    assert item.pop('gsiA1PartitionKey') == 'media/pid2'
    assert item.pop('gsiA1SortKey') == '-'
    assert item.pop('userId') == 'uid2'
    assert item.pop('postId') == 'pid2'
    assert item.pop('mediaId') == 'mid2'
    assert item.pop('mediaType') == 'IMAGE'
    assert pendulum.parse(item.pop('postedAt')) == posted_at
    assert item.pop('takenInReal') is True
    assert item.pop('originalFormat') == 'of'
    assert item.pop('imageFormat') == 'if'
    assert item == {}


def test_media_set_height_and_width(post_image_dynamo, image_item):
    media_id = image_item['mediaId']
    assert 'height' not in image_item
    assert 'width' not in image_item

    item = post_image_dynamo.set_height_and_width(media_id, 4, 2)
    assert item['height'] == 4
    assert item['width'] == 2

    item = post_image_dynamo.set_height_and_width(media_id, 120, 2000)
    assert item['height'] == 120
    assert item['width'] == 2000


def test_generate_by_post(post_image_dynamo, image_item):
    post_id_with = image_item['postId']
    post_id_without = post_id_with + 'nopenope'

    assert list(post_image_dynamo.generate_by_post(post_id_without)) == []
    assert list(post_image_dynamo.generate_by_post(post_id_with)) == [image_item]


def test_set_colors(post_image_dynamo, image_item):
    media_id = image_item['mediaId']
    assert 'colors' not in image_item

    # no support for deleting colors
    with pytest.raises(AssertionError):
        post_image_dynamo.set_colors(media_id, None)
    with pytest.raises(AssertionError):
        post_image_dynamo.set_colors(media_id, ())
    assert post_image_dynamo.get(media_id) == image_item

    # sample output from ColorTheif
    colors = [
        (52, 58, 46),
        (186, 206, 228),
        (144, 154, 170),
        (158, 180, 205),
        (131, 125, 125),
    ]

    new_item = post_image_dynamo.set_colors(media_id, colors)
    assert post_image_dynamo.get(media_id) == new_item
    assert new_item['colors'] == [
        {'r': 52, 'g': 58, 'b': 46},
        {'r': 186, 'g': 206, 'b': 228},
        {'r': 144, 'g': 154, 'b': 170},
        {'r': 158, 'g': 180, 'b': 205},
        {'r': 131, 'g': 125, 'b': 125},
    ]
    del new_item['colors']
    assert new_item == image_item
