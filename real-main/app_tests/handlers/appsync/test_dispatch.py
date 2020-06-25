import os

import pytest

# turning off route autodiscovery
os.environ['APPSYNC_ROUTE_AUTODISCOVERY_PATH'] = ''
from app.handlers.appsync import dispatch, routes  # noqa: E402 isort:skip


@pytest.fixture
def cognito_authed_event():
    yield {
        'field': 'Type.field',
        'arguments': ['arg1', 'arg2'],
        'identity': {'cognitoIdentityId': '42-42'},
        'source': {'anotherField': 42},
        'headers': {'x-real-version': '1.2.3(456)'},
    }


@pytest.fixture
def api_key_authed_event():
    yield {
        'field': 'Type.field',
        'arguments': ['arg1', 'arg2'],
        'identity': {},
        'source': {'anotherField': 42},
        'headers': {},
    }


@pytest.fixture
def setup_one_route():
    routes.clear()

    @routes.register('Type.field')
    def mocked_handler(caller_user_id, arguments, source, context):  # pylint: disable=unused-variable
        return {
            'caller_user_id': caller_user_id,
            'arguments': arguments,
            'source': source,
        }


def test_unknown_field_raises_exception(setup_one_route, cognito_authed_event):
    cognito_authed_event['field'] = 'Type.unknownField'
    with pytest.raises(Exception, match='No handler for field `Type.unknownField` found'):
        dispatch(cognito_authed_event, {})


def test_basic_success(setup_one_route, cognito_authed_event):
    resp = dispatch(cognito_authed_event, {})
    assert resp == {
        'success': {'caller_user_id': '42-42', 'arguments': ['arg1', 'arg2'], 'source': {'anotherField': 42}},
    }


def test_no_source(setup_one_route, cognito_authed_event):
    cognito_authed_event['source'] = None
    resp = dispatch(cognito_authed_event, {})
    assert resp == {
        'success': {'caller_user_id': '42-42', 'arguments': ['arg1', 'arg2'], 'source': None},
    }


def test_api_key_authenticated(setup_one_route, api_key_authed_event):
    resp = dispatch(api_key_authed_event, {})
    assert resp == {
        'success': {'caller_user_id': None, 'arguments': ['arg1', 'arg2'], 'source': {'anotherField': 42}},
    }
