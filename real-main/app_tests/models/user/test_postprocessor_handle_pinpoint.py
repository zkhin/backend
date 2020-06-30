from unittest.mock import call
from uuid import uuid4

import pytest

from app.models.user.enums import UserStatus


@pytest.fixture
def user_postprocessor(user_manager):
    yield user_manager.postprocessor


@pytest.fixture
def user_id():
    yield str(uuid4())


def test_handle_pinpoint_no_change(user_postprocessor, user_id):
    old_item = {'userId': user_id}
    new_item = {'userId': user_id}

    user_postprocessor.pinpoint_client.reset_mock()
    user_postprocessor.handle_pinpoint(user_id, old_item, new_item)
    assert user_postprocessor.pinpoint_client.mock_calls == []


def test_handle_pinpoint_user_delete(user_postprocessor, user_id):
    old_item = {'userId': user_id}
    new_item = {}

    user_postprocessor.pinpoint_client.reset_mock()
    user_postprocessor.handle_pinpoint(user_id, old_item, new_item)
    assert user_postprocessor.pinpoint_client.mock_calls == [call.delete_user_endpoints(user_id)]


def test_handle_pinpoint_user_disable(user_postprocessor, user_id):
    old_item = {'userId': user_id}
    new_item = {'userId': user_id, 'userStatus': UserStatus.DISABLED}

    user_postprocessor.pinpoint_client.reset_mock()
    user_postprocessor.handle_pinpoint(user_id, old_item, new_item)
    assert user_postprocessor.pinpoint_client.mock_calls == [call.disable_user_endpoints(user_id)]


def test_handle_pinpoint_user_enable(user_postprocessor, user_id):
    old_item = {'userId': user_id, 'userStatus': UserStatus.DISABLED}
    new_item = {'userId': user_id}

    user_postprocessor.pinpoint_client.reset_mock()
    user_postprocessor.handle_pinpoint(user_id, old_item, new_item)
    assert user_postprocessor.pinpoint_client.mock_calls == [call.enable_user_endpoints(user_id)]


def test_handle_pinpoint_user_deleting(user_postprocessor, user_id):
    old_item = {'userId': user_id}
    new_item = {'userId': user_id, 'userStatus': UserStatus.DELETING}

    user_postprocessor.pinpoint_client.reset_mock()
    user_postprocessor.handle_pinpoint(user_id, old_item, new_item)
    assert user_postprocessor.pinpoint_client.mock_calls == [call.delete_user_endpoints(user_id)]


@pytest.mark.parametrize('old_email', (None, 'other-real-test@real.app'))
def test_handle_pinpoint_change_set_change_user_email(user_postprocessor, user_id, old_email):
    old_item = {'userId': user_id}
    if old_email:
        old_item['email'] = old_email
    new_item = {'userId': user_id, 'email': 'real-test@real.app'}

    user_postprocessor.pinpoint_client.reset_mock()
    user_postprocessor.handle_pinpoint(user_id, old_item, new_item)
    assert user_postprocessor.pinpoint_client.mock_calls == [
        call.update_user_endpoint(user_id, 'EMAIL', 'real-test@real.app')
    ]


@pytest.mark.parametrize('old_phone', (None, '+14155551212'))
def test_handle_pinpoint_change_set_change_user_phone(user_postprocessor, user_id, old_phone):
    old_item = {'userId': user_id}
    if old_phone:
        old_item['phoneNumber'] = old_phone
    new_item = {'userId': user_id, 'phoneNumber': '+12125551212'}

    user_postprocessor.pinpoint_client.reset_mock()
    user_postprocessor.handle_pinpoint(user_id, old_item, new_item)
    assert user_postprocessor.pinpoint_client.mock_calls == [
        call.update_user_endpoint(user_id, 'SMS', '+12125551212')
    ]
