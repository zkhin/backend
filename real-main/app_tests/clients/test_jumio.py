import pytest

from app.clients import JumioClient


@pytest.fixture
def jumio_client():
    yield JumioClient(lambda: {'apiToken': 'the-api-token', 'secret': 'secret', 'callbackUrl': 'callback-url'})


def test_verify_id_success(jumio_client, requests_mock):
    # configure requests mock
    requests_mock.post(
        'https://netverify.com/api/netverify/v2/performNetverify', json={'jumioIdScanReference': 'user-id'}
    )

    # do the call
    result = jumio_client.verify_id('user-id', 'frontside-image-data', 'USA', 'PASSPORT', 'JPEG')
    assert result == 'user-id'

    # configure requests mock
    assert len(requests_mock.request_history) == 1
    req = requests_mock.request_history[0]
    assert req.method == 'POST'
    assert req.url == 'https://netverify.com/api/netverify/v2/performNetverify'
    assert req.json() == {
        'merchantIdScanReference': 'user-id',
        'frontsideImage': 'frontside-image-data',
        'country': 'USA',
        'idType': 'PASSPORT',
        'frontsideImageMimeType': 'JPEG',
        'callbackUrl': 'callback-url/id-verification/user-id/callback',
    }

    assert req._request.headers['Authorization'] == f'Basic {jumio_client.auth_token}'


def test_verify_id_handle_400_error(jumio_client, requests_mock):
    # configure requests mock
    error_msg = 'Your request was messed up'
    requests_mock.post(
        'https://netverify.com/api/netverify/v2/performNetverify', json={'errors': [error_msg], 'data': {}}
    )

    # do the call
    with pytest.raises(Exception, match=error_msg):
        jumio_client.verify_id('user-id', 'frontside-image-data', 'USA', 'PASSPORT', 'JPEG')
