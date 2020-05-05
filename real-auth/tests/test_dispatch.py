import json
import logging

import pytest

from real_auth.dispatch import ClientException, handler


def example_success(event, context):
    return {'yup': 'yup'}


def example_client_error(event, context):
    raise ClientException('client nope nope')


def example_server_error(event, context):
    raise Exception('server nope nope')


def test_success(caplog):
    event = {'event-key': 'event-data'}
    with caplog.at_level(logging.INFO):
        resp = handler(example_success)(event, None)
    assert len(caplog.records) == 1
    assert 'example_success' in caplog.records[0].msg
    assert caplog.records[0].event == event
    assert resp == {
        'statusCode': 200,
        'body': json.dumps({'yup': 'yup'}),
    }


def test_client_error(caplog):
    event = {'event-key': 'event-data'}
    with caplog.at_level(logging.INFO):
        resp = handler(example_client_error)(event, None)
    assert len(caplog.records) == 1
    assert 'example_client_error' in caplog.records[0].msg
    assert caplog.records[0].event == event
    assert resp == {
        'statusCode': 400,
        'body': json.dumps({'message': 'client nope nope'}),
    }


def test_server_error(caplog):
    event = {'event-key': 'event-data'}
    with caplog.at_level(logging.INFO):
        with pytest.raises(Exception, match='server nope nope'):
            handler(example_server_error)(event, None)
    assert len(caplog.records) == 1
    assert 'example_server_error' in caplog.records[0].msg
    assert caplog.records[0].event == event
