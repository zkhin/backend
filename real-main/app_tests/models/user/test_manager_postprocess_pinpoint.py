from unittest.mock import call
from uuid import uuid4

import pytest

from app.models.user.enums import UserStatus


@pytest.fixture
def user_id():
    yield str(uuid4())


def test_postprocess_pinpoint_no_change(user_manager, user_id):
    old_item = {'userId': {'S': user_id}}
    new_item = {'userId': {'S': user_id}}

    user_manager.pinpoint_client.reset_mock()
    user_manager.postprocess_pinpoint(user_id, old_item, new_item)
    assert user_manager.pinpoint_client.mock_calls == []


def test_postprocess_pinpoint_user_delete(user_manager, user_id):
    old_item = {'userId': {'S': user_id}}
    new_item = {}

    user_manager.pinpoint_client.reset_mock()
    user_manager.postprocess_pinpoint(user_id, old_item, new_item)
    assert user_manager.pinpoint_client.mock_calls == [call.delete_user_endpoints(user_id)]


def test_postprocess_pinpoint_user_disable(user_manager, user_id):
    old_item = {'userId': {'S': user_id}}
    new_item = {'userId': {'S': user_id}, 'userStatus': {'S': UserStatus.DISABLED}}

    user_manager.pinpoint_client.reset_mock()
    user_manager.postprocess_pinpoint(user_id, old_item, new_item)
    assert user_manager.pinpoint_client.mock_calls == [call.disable_user_endpoints(user_id)]


def test_postprocess_pinpoint_user_enable(user_manager, user_id):
    old_item = {'userId': {'S': user_id}, 'userStatus': {'S': UserStatus.DISABLED}}
    new_item = {'userId': {'S': user_id}}

    user_manager.pinpoint_client.reset_mock()
    user_manager.postprocess_pinpoint(user_id, old_item, new_item)
    assert user_manager.pinpoint_client.mock_calls == [call.enable_user_endpoints(user_id)]


def test_postprocess_pinpoint_user_deleting(user_manager, user_id):
    old_item = {'userId': {'S': user_id}}
    new_item = {'userId': {'S': user_id}, 'userStatus': {'S': UserStatus.DELETING}}

    user_manager.pinpoint_client.reset_mock()
    user_manager.postprocess_pinpoint(user_id, old_item, new_item)
    assert user_manager.pinpoint_client.mock_calls == [call.delete_user_endpoints(user_id)]


@pytest.mark.parametrize('old_email', (None, 'other-real-test@real.app'))
def test_postprocess_pinpoint_change_set_change_user_email(user_manager, user_id, old_email):
    old_item = {'userId': {'S': user_id}}
    if old_email:
        old_item['email'] = {'S': old_email}
    new_item = {'userId': {'S': user_id}, 'email': {'S': 'real-test@real.app'}}

    user_manager.pinpoint_client.reset_mock()
    user_manager.postprocess_pinpoint(user_id, old_item, new_item)
    assert user_manager.pinpoint_client.mock_calls == [
        call.update_user_endpoint(user_id, 'EMAIL', 'real-test@real.app')
    ]


@pytest.mark.parametrize('old_phone', (None, '+14155551212'))
def test_postprocess_pinpoint_change_set_change_user_phone(user_manager, user_id, old_phone):
    old_item = {'userId': {'S': user_id}}
    if old_phone:
        old_item['phoneNumber'] = {'S': old_phone}
    new_item = {'userId': {'S': user_id}, 'phoneNumber': {'S': '+12125551212'}}

    user_manager.pinpoint_client.reset_mock()
    user_manager.postprocess_pinpoint(user_id, old_item, new_item)
    assert user_manager.pinpoint_client.mock_calls == [call.update_user_endpoint(user_id, 'SMS', '+12125551212')]
