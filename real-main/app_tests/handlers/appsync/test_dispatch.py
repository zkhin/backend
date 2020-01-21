import os
import pytest

# turning off route autodiscovery
os.environ['APPSYNC_ROUTE_AUTODISCOVERY_PATH'] = ''
from app.handlers.appsync import dispatch, routes  # noqa: E402


def build_event(field, arguments, source=None, cognito_identity_id=None):
    event = {
        'field': field,
        'arguments': arguments,
    }
    if cognito_identity_id:
        event['identity'] = {
            'cognitoIdentityId': cognito_identity_id,
        }
    if source:
        event['source'] = source
    return event


@pytest.fixture
def setup_one_route():
    routes.clear()

    @routes.register('Type.field')
    def mocked_handler(caller_user_id, arguments, source, context):
        return {
            'caller_user_id': caller_user_id,
            'arguments': arguments,
            'source': source,
        }


def test_unauthenticated_raises_exception(setup_one_route):
    event = build_event('Type.field', [])
    resp = dispatch(event, {})
    assert resp == {
        'error': 'No authentication found - all calls must be authenticated'
    }


def test_unknown_field_raises_exception(setup_one_route):
    event = build_event('Type.unknownField', [], cognito_identity_id='42-42')
    resp = dispatch(event, {})
    assert resp == {
        'error': "No handler for field `Type.unknownField` found"
    }


def test_success_case(setup_one_route):
    event = build_event('Type.field', ['gogo'], cognito_identity_id='42-42')
    resp = dispatch(event, {})
    assert resp == {
        'success': {
            'caller_user_id': '42-42',
            'arguments': ['gogo'],
            'source': None,
        },
    }


def test_with_source(setup_one_route):
    event = build_event('Type.field', ['nono'], source={'y': 'n'}, cognito_identity_id='42-42')
    resp = dispatch(event, {})
    assert resp == {
        'success': {
            'caller_user_id': '42-42',
            'arguments': ['nono'],
            'source': {'y': 'n'},
        },
    }
