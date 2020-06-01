import unittest.mock as mock
import uuid

import pytest

from app.handlers.dynamo.pinpoint import update_pinpoint
from app.models.user.enums import UserStatus


@pytest.fixture
def user_id():
    yield str(uuid.uuid4())


def test_update_pinpoint_no_change(pinpoint_client, user_id):
    old_item = {'userId': {'S': user_id}}
    new_item = {'userId': {'S': user_id}}

    pinpoint_client.reset_mock()
    update_pinpoint(pinpoint_client, user_id, old_item, new_item)
    assert pinpoint_client.mock_calls == []


def test_update_pinpoint_user_delete(pinpoint_client, user_id):
    old_item = {'userId': {'S': user_id}}
    new_item = {}

    pinpoint_client.reset_mock()
    update_pinpoint(pinpoint_client, user_id, old_item, new_item)
    assert pinpoint_client.mock_calls == [mock.call.delete_user_endpoints(user_id)]


def test_update_pinpoint_user_disable(pinpoint_client, user_id):
    old_item = {'userId': {'S': user_id}}
    new_item = {'userId': {'S': user_id}, 'userStatus': {'S': UserStatus.DISABLED}}

    pinpoint_client.reset_mock()
    update_pinpoint(pinpoint_client, user_id, old_item, new_item)
    assert pinpoint_client.mock_calls == [mock.call.disable_user_endpoints(user_id)]


def test_update_pinpoint_user_enable(pinpoint_client, user_id):
    old_item = {'userId': {'S': user_id}, 'userStatus': {'S': UserStatus.DISABLED}}
    new_item = {'userId': {'S': user_id}}

    pinpoint_client.reset_mock()
    update_pinpoint(pinpoint_client, user_id, old_item, new_item)
    assert pinpoint_client.mock_calls == [mock.call.enable_user_endpoints(user_id)]


def test_update_pinpoint_user_deleting(pinpoint_client, user_id):
    user_id = str(uuid.uuid4())
    old_item = {'userId': {'S': user_id}}
    new_item = {'userId': {'S': user_id}, 'userStatus': {'S': UserStatus.DELETING}}

    pinpoint_client.reset_mock()
    update_pinpoint(pinpoint_client, user_id, old_item, new_item)
    assert pinpoint_client.mock_calls == [mock.call.delete_user_endpoints(user_id)]


@pytest.mark.parametrize('old_email', (None, 'other-real-test@real.app'))
def test_update_pinpoint_change_set_change_user_email(pinpoint_client, user_id, old_email):
    old_item = {'userId': {'S': user_id}}
    if old_email:
        old_item['email'] = {'S': old_email}
    new_item = {'userId': {'S': user_id}, 'email': {'S': 'real-test@real.app'}}

    pinpoint_client.reset_mock()
    update_pinpoint(pinpoint_client, user_id, old_item, new_item)
    assert pinpoint_client.mock_calls == [mock.call.update_user_endpoint(user_id, 'EMAIL', 'real-test@real.app')]


@pytest.mark.parametrize('old_phone', (None, '+14155551212'))
def test_update_pinpoint_change_set_change_user_phone(pinpoint_client, user_id, old_phone):
    old_item = {'userId': {'S': user_id}}
    if old_phone:
        old_item['phoneNumber'] = {'S': old_phone}
    new_item = {'userId': {'S': user_id}, 'phoneNumber': {'S': '+12125551212'}}

    pinpoint_client.reset_mock()
    update_pinpoint(pinpoint_client, user_id, old_item, new_item)
    assert pinpoint_client.mock_calls == [mock.call.update_user_endpoint(user_id, 'SMS', '+12125551212')]
