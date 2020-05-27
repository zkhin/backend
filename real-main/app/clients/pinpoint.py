import logging
import os

import boto3

PINPOINT_APPLICATION_ID = os.environ.get('PINPOINT_APPLICATION_ID')

logger = logging.getLogger()


class PinpointClient:

    def __init__(self, app_id=PINPOINT_APPLICATION_ID):
        self.app_id = app_id
        self.client = boto3.client('pinpoint')

    def set_email_endpoint(self, user_id, email):
        # call upon confirming an email
        pass

    def set_sms_endpoint(self, user_id, phone_number):
        # call upon confirming a phone number
        pass

    def disable_email_endpoint(self, user_id, email):
        # call upon completing the 'change my email' flow
        pass

    def disable_sms_endpoint(self, user_id, email):
        # call upon completing the 'change my phone number' flow
        pass

    def disable_endpoints(self, user_id):
        "Disable all of a user's endpoints"
        # call when a user is disabled
        pass

    def delete_endpoints(self, user_id):
        "Delete all of a user's endpoints"
        # call when a user is deleted/reset
        pass

    def get_user_addresses(self, user_id):
        "A dict of ChannelType: Address, one for each active endpoint of the user"
        # handle multiple endpoints of the same ChannelType?
        pass  # TODO

    def send_message(self, user_id, endpoint_id):  # specify channel_type instead of endpoint_id?
        pass  # TODO
