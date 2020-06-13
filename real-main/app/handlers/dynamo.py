import logging

from app.clients import ESSearchClient, PinpointClient
from app.logging import handler_logging
from app.models import UserManager

from . import xray

logger = logging.getLogger()
xray.patch_all()

clients = {
    'elasticsearch': ESSearchClient(),
    'pinpoint': PinpointClient(),
}

managers = {}
user_manager = managers.get('user') or UserManager(clients, managers=managers)


@handler_logging
def postprocess_records(event, context):
    for record in event['Records']:

        pk = record['dynamodb']['Keys']['partitionKey']['S']
        sk = record['dynamodb']['Keys']['sortKey']['S']
        old_item = record['dynamodb'].get('OldImage', {})
        new_item = record['dynamodb'].get('NewImage', {})

        if pk.startswith('user/') and sk == 'profile':
            user_manager.postprocess_record(pk, sk, old_item, new_item)
