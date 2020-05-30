"A test library for pinpoint designed to be run against a live Pinpoint Application"

import os
import uuid

import dotenv
import pytest

from app.clients import PinpointClient


@pytest.fixture
def pinpoint_client():
    dotenv.load_dotenv()
    app_id = os.environ.get('PINPOINT_APPLICATION_ID')
    yield PinpointClient(app_id=app_id)


@pytest.mark.skip(reason='Requires live Pinpoint Application')
def test_crud_email_endpoint(pinpoint_client):
    user_id = str(uuid.uuid4())
    email1 = str(uuid.uuid4())[:8] + '-test@real.app'
    email2 = str(uuid.uuid4())[:8] + '-test@real.app'
    assert pinpoint_client.get_user_email_endpoints(user_id) == {}

    # create an email endpoint for user, verify it exists
    endpoint_id1 = pinpoint_client.create_email_endpoint(user_id, email1)
    assert pinpoint_client.get_user_email_endpoints(user_id) == {endpoint_id1: email1}

    # verify get_user_email_endpoints() can handle multiple email endpoints for user
    # by creating another email endpoint, verify it exists
    endpoint_id2 = pinpoint_client.create_email_endpoint(user_id, email2)
    assert pinpoint_client.get_user_email_endpoints(user_id) == {endpoint_id1: email1, endpoint_id2: email2}

    # delete first email endpoint, verify it's gone
    pinpoint_client.delete_endpoint(endpoint_id1)
    assert pinpoint_client.get_user_email_endpoints(user_id) == {endpoint_id2: email2}

    # delete second email endpoint, verify it's gone
    pinpoint_client.delete_endpoint(endpoint_id2)
    assert pinpoint_client.get_user_email_endpoints(user_id) == {}


@pytest.mark.skip(reason='Requires live Pinpoint Application')
def test_crud_sms_endpoint(pinpoint_client):
    user_id = str(uuid.uuid4())
    phone1 = '+12125551212'
    phone2 = '+14155551212'
    assert pinpoint_client.get_user_sms_endpoints(user_id) == {}

    # create an sms endpoint for user, verify it exists
    endpoint_id1 = pinpoint_client.create_sms_endpoint(user_id, phone1)
    assert pinpoint_client.get_user_sms_endpoints(user_id) == {endpoint_id1: phone1}

    # verify get_user_sms_endpoints() can handle multiple sms endpoints for user
    # by creating another sms endpoint, verify it exists
    endpoint_id2 = pinpoint_client.create_sms_endpoint(user_id, phone2)
    assert pinpoint_client.get_user_sms_endpoints(user_id) == {endpoint_id1: phone1, endpoint_id2: phone2}

    # delete first sms endpoint, verify it's gone
    pinpoint_client.delete_endpoint(endpoint_id1)
    assert pinpoint_client.get_user_sms_endpoints(user_id) == {endpoint_id2: phone2}

    # delete second sms endpoint, verify it's gone
    pinpoint_client.delete_endpoint(endpoint_id2)
    assert pinpoint_client.get_user_sms_endpoints(user_id) == {}


@pytest.mark.skip(reason='Requires live Pinpoint Application')
def test_delete_user_endpoints(pinpoint_client):
    user_id = str(uuid.uuid4())
    email = str(uuid.uuid4())[:8] + '-test@real.app'
    phone = '+14155551212'

    # create an sms endpoint and an email enpoint for the user, verify they exist
    endpoint_id1 = pinpoint_client.create_sms_endpoint(user_id, email)
    endpoint_id2 = pinpoint_client.create_sms_endpoint(user_id, phone)
    assert pinpoint_client.get_user_sms_endpoints(user_id) == {endpoint_id1: email, endpoint_id2: phone}

    # delete them, verify they're gone
    pinpoint_client.delete_user_endpoints(user_id)
    assert pinpoint_client.get_user_sms_endpoints(user_id) == {}
