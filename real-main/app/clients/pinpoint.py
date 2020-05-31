import logging
import os
import uuid

import boto3

PINPOINT_APPLICATION_ID = os.environ.get('PINPOINT_APPLICATION_ID')

logger = logging.getLogger()


class PinpointClient:

    def __init__(self, app_id=PINPOINT_APPLICATION_ID):
        self.app_id = app_id
        self.client = boto3.client('pinpoint')

    def update_user_endpoint(self, user_id, channel_type, address):
        """
        Set the user's endpoint of type `channel_type` to `address.

        The user should have at most one active endpoint of each `channel_type`.
        If this method finds more than one active endpoint for the given
        `channel_type`, it will set `address` on one of them and delete the extras.
        """
        endpoints = self.get_user_endpoints(user_id, channel_type=channel_type)
        endpoint_ids = []
        for this_endpoint_id, this_address in endpoints.items():
            # put the endpoint to keep at the front
            if this_address == address:
                endpoint_ids.insert(0, this_endpoint_id)
            else:
                endpoint_ids.append(this_endpoint_id)

        # delete extras
        while (len(endpoint_ids) > 1):
            self.delete_endpoint(endpoint_ids.pop())

        endpoint_id = endpoint_ids[0] if endpoint_ids else str(uuid.uuid4())
        if endpoints.get(endpoint_id) != address:
            kwargs = {
                'ApplicationId': self.app_id,
                'EndpointId': endpoint_id,
                'EndpointRequest': {
                    'Address': address,
                    'ChannelType': channel_type,
                    'User': {
                        'UserId': user_id,
                    }
                }
            }
            self.client.update_endpoint(**kwargs)
        return endpoint_id

    def get_user_endpoints(self, user_id, channel_type=None):
        "A dict of {endpoint_id: address}"
        kwargs = {
            'ApplicationId': self.app_id,
            'UserId': user_id,
        }
        try:
            resp = self.client.get_user_endpoints(**kwargs)
        except self.client.exceptions.NotFoundException:
            return {}

        conditions = [lambda item: item['EndpointStatus'] == 'ACTIVE']
        if channel_type:
            conditions.append(lambda item: item['ChannelType'] == channel_type)

        return {
            item['Id']: item['Address']
            for item in resp['EndpointsResponse']['Item']
            if all(condition(item) for condition in conditions)
        }

    def delete_endpoint(self, endpoint_id):
        "Delete a specific endpoint"
        kwargs = {
            'ApplicationId': self.app_id,
            'EndpointId': endpoint_id,
        }
        self.client.delete_endpoint(**kwargs)

    def delete_user_endpoint(self, user_id, channel_type):
        "Delete a user's endpoint of a specific `channel_type`"
        endpoints = self.get_user_endpoints(user_id, channel_type=channel_type)
        for endpoint_id, _ in endpoints.items():
            self.delete_endpoint(endpoint_id)

    def delete_user_endpoints(self, user_id):
        "Delete all of a user's endpoints"
        kwargs = {
            'ApplicationId': self.app_id,
            'UserId': user_id,
        }
        self.client.delete_user_endpoints(**kwargs)
