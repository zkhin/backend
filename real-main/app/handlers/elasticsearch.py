import logging

from app.clients import ESSearchClient
from app.logging import handler_logging

from . import xray

logger = logging.getLogger()
xray.patch_all()

elasticsearch_client = ESSearchClient()


@handler_logging
def dynamodb_stream(event, context):
    for record in event['Records']:
        # only user profile records
        sortKey = record['dynamodb']['Keys']['sortKey']['S']
        if sortKey != 'profile':
            continue

        new_user_item = record['dynamodb'].get('NewImage', {})
        old_user_item = record['dynamodb'].get('OldImage', {})

        # if we're manually rebuilding the index, treat everything as new
        new_reindexed_at = new_user_item.get('lastManuallyReindexedAt')
        old_reindexed_at = old_user_item.get('lastManuallyReindexedAt')
        if new_reindexed_at and new_reindexed_at != old_reindexed_at:
            old_user_item = {}

        if new_user_item and old_user_item:
            elasticsearch_client.update_user(old_user_item, new_user_item)
        elif new_user_item:
            elasticsearch_client.add_user(new_user_item)
        elif old_user_item:
            elasticsearch_client.delete_user(old_user_item)
        else:
            logger.warning(f'No new or old images found dynamo record: {record}')
