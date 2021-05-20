from decimal import Decimal

import pytest

from app.clients import IdAnalyzerClient


@pytest.fixture
def id_analyzer_client():
    yield IdAnalyzerClient(lambda: {'apiKey': 'the-api-key'})


def test_verify_id_success(id_analyzer_client, requests_mock):
    # configure requests mock
    requests_mock.post('https://api.idanalyzer.com', json={'authentication': {'score': 0.8}})

    # do the call
    result = id_analyzer_client.verify_id('frontside-image-data')
    assert result == {'authentication': {'score': Decimal('0.8')}, 'result': {}}

    # configure requests mock
    assert len(requests_mock.request_history) == 1
    req = requests_mock.request_history[0]
    assert req.method == 'POST'
    assert req.url == 'https://api.idanalyzer.com/'
    assert req.json() == {
        'apikey': 'the-api-key',
        'file_base64': 'frontside-image-data',
        'authenticate': True,
    }


def test_verify_id_handle_400_error(id_analyzer_client, requests_mock):
    # configure requests mock
    error_msg = 'Your request was messed up'
    requests_mock.post(
        'https://api.idanalyzer.com', json={'error': {'code': 400, 'message': error_msg}, 'data': {}}
    )

    # do the call
    with pytest.raises(Exception, match=error_msg):
        id_analyzer_client.verify_id('frontside-image-data')
