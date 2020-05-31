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
@pytest.mark.parametrize('channel_type, address1, address2', (
    ('EMAIL', 'pinpoint-test@real.app', 'pinpoint-test2@real.app'),
    ('SMS', '+14155551212', '+12125551212'),
    ('APNS', 'apns-token-1', 'apns-token-2'),
))
def test_update_and_delete_user_endpoint(pinpoint_client, channel_type, address1, address2):
    user_id = str(uuid.uuid4())
    assert pinpoint_client.get_user_endpoints(user_id, channel_type=channel_type) == {}

    # create an endpoint, verify it exists
    endpoint_id1 = pinpoint_client.update_user_endpoint(user_id, channel_type, address1)
    assert pinpoint_client.get_user_endpoints(user_id, channel_type=channel_type) == {endpoint_id1: address1}

    # no-op update the endpoint
    resp = pinpoint_client.update_user_endpoint(user_id, channel_type, address1)
    assert resp == endpoint_id1
    assert pinpoint_client.get_user_endpoints(user_id, channel_type=channel_type) == {endpoint_id1: address1}

    # update the endpoint, to a new address
    resp = pinpoint_client.update_user_endpoint(user_id, channel_type, address2)
    assert resp == endpoint_id1
    assert pinpoint_client.get_user_endpoints(user_id, channel_type=channel_type) == {endpoint_id1: address2}

    # sneak behind our client's back and create a second endpoint of same type
    endpoint_id2 = str(uuid.uuid4())
    kwargs = {
        'ApplicationId': pinpoint_client.app_id,
        'EndpointId': endpoint_id2,
        'EndpointRequest': {
            'Address': address1,
            'ChannelType': channel_type,
            'User': {
                'UserId': user_id,
            }
        }
    }
    pinpoint_client.client.update_endpoint(**kwargs)
    assert pinpoint_client.get_user_endpoints(user_id, channel_type=channel_type) == {
        endpoint_id1: address2,
        endpoint_id2: address1,
    }

    # update the endpoint again, verify that the extra endpoint is deleted as clean-up
    resp = pinpoint_client.update_user_endpoint(user_id, channel_type, address1)
    assert resp == endpoint_id2
    assert pinpoint_client.get_user_endpoints(user_id, channel_type=channel_type) == {endpoint_id2: address1}

    # delete all endpoints of that type
    pinpoint_client.delete_user_endpoint(user_id, channel_type)
    assert pinpoint_client.get_user_endpoints(user_id, channel_type=channel_type) == {}


@pytest.mark.skip(reason='Requires live Pinpoint Application')
def test_delete_user_endpoints(pinpoint_client):
    user_id = str(uuid.uuid4())
    email = str(uuid.uuid4())[:8] + '-test@real.app'
    phone = '+14155551212'

    # create an sms endpoint and an email enpoint for the user, verify they exist
    endpoint_id1 = pinpoint_client.update_user_endpoint(user_id, 'EMAIL', email)
    endpoint_id2 = pinpoint_client.update_user_endpoint(user_id, 'SMS', phone)
    assert pinpoint_client.get_user_endpoints(user_id) == {endpoint_id1: email, endpoint_id2: phone}

    # delete them, verify they're gone
    pinpoint_client.delete_user_endpoints(user_id)
    assert pinpoint_client.get_user_endpoints(user_id) == {}
