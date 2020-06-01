import logging

from app.clients import ESSearchClient, PinpointClient
from app.logging import handler_logging

from .. import xray
from .elasticsearch import update_elasticsearch
from .pinpoint import update_pinpoint

logger = logging.getLogger()
xray.patch_all()

elasticsearch_client = ESSearchClient()
pinpoint_client = PinpointClient()


@handler_logging
def dynamo_stream(event, context):
    for record in event['Records']:
        # only process user profile records
        pk = record['dynamodb']['Keys']['partitionKey']['S']
        sk = record['dynamodb']['Keys']['sortKey']['S']
        if not pk.startswith('user/') or sk != 'profile':
            continue

        user_id = pk[len('user/'):]
        old_user_item = record['dynamodb'].get('OldImage', {})
        new_user_item = record['dynamodb'].get('NewImage', {})

        update_elasticsearch(elasticsearch_client, old_user_item, new_user_item)
        update_pinpoint(pinpoint_client, user_id, old_user_item, new_user_item)
