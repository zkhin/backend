import json

from moto import mock_secretsmanager
import pytest

from app.clients import SecretsManagerClient
from app.models.media.dynamo import MediaDynamo
from app.models.media.model import Media
from app.models.media.exceptions import MediaException

mock_api_key = 'the-api-key'
mock_root_api_url = 'https://mockmock.mock'


@pytest.fixture
def secrets_manager_client():
    with mock_secretsmanager():
        post_verification_name = 'KeyForPV'
        post_verification_secret_string = json.dumps({
            'key': mock_api_key,
            'root': mock_root_api_url,
        })
        client = SecretsManagerClient(post_verification_api_creds_name=post_verification_name)
        client.boto_client.create_secret(Name=post_verification_name, SecretString=post_verification_secret_string)
        yield client


@pytest.fixture
def clients(secrets_manager_client, cloudfront_client):
    yield {
        'secrets_manager_client': secrets_manager_client,
        'cloudfront_client': cloudfront_client,
    }


@pytest.fixture
def media_dynamo(dynamo_client):
    yield MediaDynamo(dynamo_client)


@pytest.fixture
def media_no_meta(media_dynamo, clients):
    media_id = 'media-id-1'
    kwargs = {
        'Item': {
            'partitionKey': f'media/{media_id}',
            'sortKey': '-',
            'userId': 'a-user-id',
            'postId': 'a-post-id',
            'mediaId': media_id,
            'mediaType': 'IMAGE',
        },
    }
    media_item = media_dynamo.client.add_item(kwargs)
    yield Media(media_item, media_dynamo, **clients)


@pytest.fixture
def media_all_meta(media_dynamo, clients):
    media_id = 'media-id-2'
    kwargs = {
        'Item': {
            'partitionKey': f'media/{media_id}',
            'sortKey': '-',
            'userId': 'a-user-id',
            'postId': 'a-post-id',
            'mediaId': media_id,
            'mediaType': 'IMAGE',
            'takenInReal': True,
            'originalFormat': 'HEIC',
        },
    }
    media_item = media_dynamo.client.add_item(kwargs)
    yield Media(media_item, media_dynamo, **clients)


def test_request_format_no_meta(cloudfront_client, media_no_meta, requests_mock):
    api_url = mock_root_api_url + 'verify/image'
    image_url = 'https://the-image.com'
    cloudfront_client.configure_mock(**{
        'generate_presigned_url.return_value': image_url,
    })

    resp_json = {
        'errors': [],
        'data': {
            'isVerified': False,
        }
    }
    requests_mock.post(api_url, json=resp_json)
    media_no_meta.set_is_verified()

    # check the media was updated as expected
    assert media_no_meta.item['isVerified'] is False
    media_no_meta.refresh_item()
    assert media_no_meta.item['isVerified'] is False

    # assert the call to the post verification service was as expected
    assert len(requests_mock.request_history) == 1
    req = requests_mock.request_history[0]
    assert req.method == 'POST'
    assert req.url == api_url
    assert req.json() == {
        'metadata': {},
        'url': image_url,
    }
    assert req._request.headers['x-api-key'] == mock_api_key


def test_request_format_all_meta(cloudfront_client, media_all_meta, requests_mock):
    api_url = mock_root_api_url + 'verify/image'
    image_url = 'https://the-image.com'
    cloudfront_client.configure_mock(**{
        'generate_presigned_url.return_value': image_url,
    })

    resp_json = {
        'errors': [],
        'data': {
            'isVerified': True,
        }
    }
    requests_mock.post(api_url, json=resp_json)
    media_all_meta.set_is_verified()

    # check the media was updated as expected
    assert media_all_meta.item['isVerified'] is True
    media_all_meta.refresh_item()
    assert media_all_meta.item['isVerified'] is True

    # assert the call to the post verification service was as expected
    assert len(requests_mock.request_history) == 1
    req = requests_mock.request_history[0]
    assert req.method == 'POST'
    assert req.url == api_url
    assert req.json() == {
        'metadata': {
            'takenInReal': True,
            'originalFormat': 'HEIC',
        },
        'url': image_url,
    }
    assert req._request.headers['x-api-key'] == mock_api_key


def test_response_handle_400_error(cloudfront_client, media_no_meta, requests_mock):
    api_url = mock_root_api_url + 'verify/image'
    image_url = 'https://the-image.com'
    cloudfront_client.configure_mock(**{
        'generate_presigned_url.return_value': image_url,
    })

    error_msg = 'Your request was messed up'
    resp_json = {
        'errors': [error_msg],
        'data': {},
    }
    requests_mock.post(api_url, status_code=400, json=resp_json)

    try:
        media_no_meta.set_is_verified()
    except MediaException as err:
        assert error_msg in str(err)
        assert '400' in str(err)

    # check the media was not updated
    assert 'isVerified' not in media_no_meta.item
    media_no_meta.refresh_item()
    assert 'isVerified' not in media_no_meta.item


def test_response_handle_wrong_response_format(cloudfront_client, media_no_meta, requests_mock):
    api_url = mock_root_api_url + 'verify/image'
    image_url = 'https://the-image.com'
    cloudfront_client.configure_mock(**{
        'generate_presigned_url.return_value': image_url,
    })

    resp_json = {
        'errors': [],
    }
    requests_mock.post(api_url, status_code=200, json=resp_json)

    try:
        media_no_meta.set_is_verified()
    except MediaException as err:
        assert 'errors' in str(err)
        assert 'parse' in str(err)

    # check the media was not updated
    assert 'isVerified' not in media_no_meta.item
    media_no_meta.refresh_item()
    assert 'isVerified' not in media_no_meta.item
