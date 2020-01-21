import pytest

from app.models.media.enums import MediaType
from app.models.media import MediaManager
from app.models.post import PostManager


@pytest.fixture
def media_manager(dynamo_client, s3_client):
    yield MediaManager({'dynamo': dynamo_client, 's3_uploads': s3_client})


@pytest.fixture
def post_manager(dynamo_client):
    yield PostManager({'dynamo': dynamo_client})


@pytest.fixture
def media_awaiting_upload(media_manager, post_manager):
    media_uploads = [{'mediaId': 'mid', 'mediaType': MediaType.IMAGE}]
    post = post_manager.add_post('uid', 'pid', media_uploads=media_uploads)
    media_item = post.item['mediaObjects'][0]
    yield media_manager.init_media(media_item)
