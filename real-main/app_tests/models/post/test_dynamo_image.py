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
    # add the post iamge
    transact = post_image_dynamo.transact_add('pid1')
    post_image_dynamo.client.transact_write_items([transact])

    # check format
    item = post_image_dynamo.get('pid1')
    assert item.pop('schemaVersion') == 0
    assert item.pop('partitionKey') == 'post/pid1'
    assert item.pop('sortKey') == 'image'
    assert item == {}

    # verify we can't add it again
    with pytest.raises(post_image_dynamo.client.exceptions.ConditionalCheckFailedException):
        post_image_dynamo.client.transact_write_items([transact])


def test_transact_add_maximal(post_image_dynamo):
    # add the post iamge
    transact = post_image_dynamo.transact_add('pid2', taken_in_real=True, original_format='of', image_format='if')
    post_image_dynamo.client.transact_write_items([transact])

    # check format
    item = post_image_dynamo.get('pid2')
    assert item.pop('schemaVersion') == 0
    assert item.pop('partitionKey') == 'post/pid2'
    assert item.pop('sortKey') == 'image'
    assert item.pop('takenInReal') is True
    assert item.pop('originalFormat') == 'of'
    assert item.pop('imageFormat') == 'if'
    assert item == {}


def test_media_set_height_and_width(post_image_dynamo, image_item):
    post_id = image_item['partitionKey'][5:]
    media_id = image_item.get('mediaId')
    assert 'height' not in image_item
    assert 'width' not in image_item

    item = post_image_dynamo.set_height_and_width(post_id, media_id, 4, 2)
    assert item['height'] == 4
    assert item['width'] == 2

    item = post_image_dynamo.set_height_and_width(post_id, media_id, 120, 2000)
    assert item['height'] == 120
    assert item['width'] == 2000


def test_generate_by_post(post_image_dynamo):
    media_id = 'mid'
    post_id = 'pid'

    # test none
    assert list(post_image_dynamo.generate_by_post(post_id)) == []

    # add an old-style media item to the db
    item = {
        'partitionKey': {'S': f'media/{media_id}'},
        'sortKey': {'S': '-'},
        'gsiA1PartitionKey': {'S': f'media/{post_id}'},
        'gsiA1SortKey': {'S': '-'},
        'mediaId': {'S': media_id},
        'postId': {'S': post_id},
    }
    transact = {'Put': {
        'Item': item,
        'ConditionExpression': 'attribute_not_exists(partitionKey)',  # no updates, just adds
    }}
    post_image_dynamo.client.transact_write_items([transact])

    # generate it
    items = list(post_image_dynamo.generate_by_post(post_id))
    assert len(items) == 1
    assert items[0]['mediaId'] == media_id
    assert items[0]['postId'] == post_id


def test_set_colors(post_image_dynamo, image_item):
    post_id = image_item['partitionKey'][5:]
    media_id = image_item.get('mediaId')
    assert 'colors' not in image_item

    # no support for deleting colors
    with pytest.raises(AssertionError):
        post_image_dynamo.set_colors(post_id, media_id, None)
    with pytest.raises(AssertionError):
        post_image_dynamo.set_colors(post_id, media_id, ())
    assert post_image_dynamo.get(post_id) == image_item

    # sample output from ColorTheif
    colors = [
        (52, 58, 46),
        (186, 206, 228),
        (144, 154, 170),
        (158, 180, 205),
        (131, 125, 125),
    ]

    new_item = post_image_dynamo.set_colors(post_id, media_id, colors)
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
