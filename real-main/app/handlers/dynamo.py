import logging

from app import clients, models
from app.logging import LogLevelContext, handler_logging

from . import xray

logger = logging.getLogger()
xray.patch_all()

clients = {
    'appsync': clients.AppSyncClient(),
    'dynamo': clients.DynamoClient(),
    'elasticsearch': clients.ESSearchClient(),
    'pinpoint': clients.PinpointClient(),
}

managers = {}
user_manager = managers.get('user') or models.UserManager(clients, managers=managers)
chat_message_manager = managers.get('chat_message') or models.ChatMessageManager(clients, managers=managers)


@handler_logging
def postprocess_records(event, context):
    for record in event['Records']:

        pk = record['dynamodb']['Keys']['partitionKey']['S']
        sk = record['dynamodb']['Keys']['sortKey']['S']
        old_item = record['dynamodb'].get('OldImage', {})
        new_item = record['dynamodb'].get('NewImage', {})

        op = 'edit' if old_item and new_item else 'add' if not old_item else 'delete' if not new_item else 'unknown'
        with LogLevelContext(logger, logging.INFO):
            logger.info(f'Post-processing `{op}` operation of record `{pk}`, `{sk}`')

        if pk.startswith('user/') and sk == 'profile':
            try:
                user_manager.postprocess_record(pk, sk, old_item, new_item)
            except Exception as err:
                logger.exception(str(err))

        if pk.startswith('chatMessage/') and sk == '-':
            try:
                chat_message_manager.postprocess_record(pk, sk, old_item, new_item)
            except Exception as err:
                logger.exception(str(err))
