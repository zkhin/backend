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

    def create_email_endpoint(self, user_id, email):
        endpoint_id = str(uuid.uuid4())
        kwargs = {
            'ApplicationId': self.app_id,
            'EndpointId': endpoint_id,
            'EndpointRequest': {
                'Address': email,
                'ChannelType': 'EMAIL',
                'User': {
                    'UserId': user_id,
                }
            }
        }
        self.client.update_endpoint(**kwargs)
        return endpoint_id

    def create_sms_endpoint(self, user_id, phone_number):
        endpoint_id = str(uuid.uuid4())
        kwargs = {
            'ApplicationId': self.app_id,
            'EndpointId': endpoint_id,
            'EndpointRequest': {
                'Address': phone_number,
                'ChannelType': 'SMS',
                'User': {
                    'UserId': user_id,
                }
            }
        }
        self.client.update_endpoint(**kwargs)
        return endpoint_id

    def get_user_email_endpoints(self, user_id):
        "A dict of {endpoint_id: email_address}"
        kwargs = {
            'ApplicationId': self.app_id,
            'UserId': user_id,
        }
        try:
            resp = self.client.get_user_endpoints(**kwargs)
        except self.client.exceptions.NotFoundException:
            return {}
        return {
            item['Id']: item['Address']
            for item in resp['EndpointsResponse']['Item']
            if item['ChannelType'] == 'EMAIL' and item['EndpointStatus'] == 'ACTIVE'
        }

    def get_user_sms_endpoints(self, user_id):
        "A dict of {endpoint_id: email_address}"
        kwargs = {
            'ApplicationId': self.app_id,
            'UserId': user_id,
        }
        try:
            resp = self.client.get_user_endpoints(**kwargs)
        except self.client.exceptions.NotFoundException:
            return {}
        return {
            item['Id']: item['Address']
            for item in resp['EndpointsResponse']['Item']
            if item['ChannelType'] == 'SMS' and item['EndpointStatus'] == 'ACTIVE'
        }

    def delete_endpoint(self, endpoint_id):
        kwargs = {
            'ApplicationId': self.app_id,
            'EndpointId': endpoint_id,
        }
        self.client.delete_endpoint(**kwargs)

    def delete_user_endpoints(self, user_id):
        "Delete all of a user's endpoints"
        kwargs = {
            'ApplicationId': self.app_id,
            'UserId': user_id,
        }
        self.client.delete_user_endpoints(**kwargs)
