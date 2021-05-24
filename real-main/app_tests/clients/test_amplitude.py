import logging

import pytest
import requests_mock

from app.clients import AmplitudeClient

url = 'https://api2.amplitude.com/2/httpapi'
api_key = 'the-api-key'


@pytest.fixture
def client():
    yield AmplitudeClient(lambda: {'apiKey': api_key})


def test_send_events_correct_request_sent(client):
    # send some events
    events = [{'e': 1}, {'e': 2}]
    with requests_mock.Mocker() as m:
        m.post(url)
        client.send_events(events)

    # verify correct network request was made
    assert len(m.request_history) == 1
    assert m.request_history[0].method == 'POST'
    assert m.request_history[0].json() == {
        'api_key': api_key,
        'events': events,
    }


def test_send_events_handle_success_response(client, caplog):
    # send some events, mock success response
    with caplog.at_level(logging.WARNING), requests_mock.Mocker() as m:
        m.post(url, status_code=200)
        client.send_events([])

    # verify no warnings were logged
    assert len(caplog.records) == 0


@pytest.mark.parametrize('status_code', [400, 500])
def test_send_events_handle_error_response(client, caplog, status_code):
    # send some events, mock error response
    with caplog.at_level(logging.WARNING), requests_mock.Mocker() as m:
        m.post(url, status_code=status_code)
        client.send_events([])

    # verify a warning was logged
    assert len(caplog.records) == 1
    assert 'Failed to send events to Amplitude' in caplog.records[0].msg
