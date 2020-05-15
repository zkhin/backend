import uuid

import pytest

from app.models.post.dynamo import PostImageDynamo


@pytest.fixture
def post_image_dynamo(dynamo_client):
    yield PostImageDynamo(dynamo_client)


@pytest.fixture
def image_item(post_image_dynamo):
    post_id = str(uuid.uuid4())
    transact = post_image_dynamo.transact_add(post_id)
    post_image_dynamo.client.transact_write_items([transact])
    yield post_image_dynamo.get(post_id)


def test_transact_add_minimal(post_image_dynamo):
    # add the post image
    transact = post_image_dynamo.transact_add('pid1')
    post_image_dynamo.client.transact_write_items([transact])

    # check format
    item = post_image_dynamo.get('pid1')
    assert item.pop('schemaVersion') == 0
    assert item.pop('partitionKey') == 'post/pid1'
    assert item.pop('sortKey') == 'image'
    assert item == {}

    # verify we can't add it again
    with pytest.raises(post_image_dynamo.client.exceptions.TransactionCanceledException):
        post_image_dynamo.client.transact_write_items([transact])


def test_transact_add_maximal(post_image_dynamo):
    # add the post image
    crop = {'upperLeft': {'x': 1, 'y': 2}, 'lowerRight': {'x': 3, 'y': 4}}
    transact = post_image_dynamo.transact_add('pid2', crop=crop, image_format='if', original_format='of',
                                              taken_in_real=True)
    post_image_dynamo.client.transact_write_items([transact])

    # check format
    item = post_image_dynamo.get('pid2')
    assert item.pop('schemaVersion') == 0
    assert item.pop('partitionKey') == 'post/pid2'
    assert item.pop('sortKey') == 'image'
    assert item.pop('crop') == crop
    assert item.pop('imageFormat') == 'if'
    assert item.pop('originalFormat') == 'of'
    assert item.pop('takenInReal') is True
    assert item == {}


def test_transact_add_doesnt_add_non_positive_crops(post_image_dynamo):
    # add two post images with different crops
    crop1 = {'upperLeft': {'x': -1, 'y': 0}, 'lowerRight': {'x': 1, 'y': 2}}
    crop2 = {'upperLeft': {'x': 2, 'y': 1}, 'lowerRight': {'x': 0, 'y': -1}}

    post_image_dynamo.client.transact_write_items([
        post_image_dynamo.transact_add('pid1', crop=crop1),
        post_image_dynamo.transact_add('pid2', crop=crop2),
    ])

    # check format first one
    item = post_image_dynamo.get('pid1')
    assert item['partitionKey'] == 'post/pid1'
    assert item['crop'] == crop1

    # check format second one
    item = post_image_dynamo.get('pid2')
    assert item['partitionKey'] == 'post/pid2'
    assert item['crop'] == crop2


def test_delete(post_image_dynamo):
    post_id = 'pid1'
    assert post_image_dynamo.get(post_id) is None

    # deleting an item that doesn't exist fails softly
    post_image_dynamo.delete(post_id)
    assert post_image_dynamo.get(post_id) is None

    # add the post image, verify
    transact = post_image_dynamo.transact_add(post_id)
    post_image_dynamo.client.transact_write_items([transact])
    assert post_image_dynamo.get(post_id)

    # delete it, verify
    post_image_dynamo.delete(post_id)
    assert post_image_dynamo.get(post_id) is None


def test_media_set_height_and_width(post_image_dynamo, image_item):
    post_id = image_item['partitionKey'][5:]
    assert 'height' not in image_item
    assert 'width' not in image_item

    item = post_image_dynamo.set_height_and_width(post_id, 4, 2)
    assert item['height'] == 4
    assert item['width'] == 2

    item = post_image_dynamo.set_height_and_width(post_id, 120, 2000)
    assert item['height'] == 120
    assert item['width'] == 2000


def test_set_colors(post_image_dynamo, image_item):
    post_id = image_item['partitionKey'][5:]
    assert 'colors' not in image_item

    # no support for deleting colors
    with pytest.raises(AssertionError):
        post_image_dynamo.set_colors(post_id, None)
    with pytest.raises(AssertionError):
        post_image_dynamo.set_colors(post_id, ())
    assert post_image_dynamo.get(post_id) == image_item

    # sample output from ColorTheif
    colors = [
        (52, 58, 46),
        (186, 206, 228),
        (144, 154, 170),
        (158, 180, 205),
        (131, 125, 125),
    ]

    new_item = post_image_dynamo.set_colors(post_id, colors)
    assert post_image_dynamo.get(post_id) == new_item
    assert new_item['colors'] == [
        {'r': 52, 'g': 58, 'b': 46},
        {'r': 186, 'g': 206, 'b': 228},
        {'r': 144, 'g': 154, 'b': 170},
        {'r': 158, 'g': 180, 'b': 205},
        {'r': 131, 'g': 125, 'b': 125},
    ]
    del new_item['colors']
    assert new_item == image_item
