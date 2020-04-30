import pytest

from app.models.post.enums import PostType


@pytest.fixture
def media(post_manager):
    yield post_manager.add_post('uid', 'pid', PostType.IMAGE).media


def test_refresh_item(dynamo_client, media):
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
