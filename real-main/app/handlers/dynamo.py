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
chat_manager = managers.get('chat') or models.ChatManager(clients, managers=managers)
chat_message_manager = managers.get('chat_message') or models.ChatMessageManager(clients, managers=managers)
follow_manager = managers.get('follow') or models.FollowManager(clients, managers=managers)


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

        postprocess_record = None

        if pk.startswith('user/') and sk == 'profile':
            postprocess_record = user_manager.postprocess_record

        if pk.startswith('chat/'):
            postprocess_record = chat_manager.postprocess_record

        if pk.startswith('chatMessage/'):
            postprocess_record = chat_message_manager.postprocess_record

        if pk.startswith('following/') or (pk.startswith('user/') and sk.startswith('follower/')):
            postprocess_record = follow_manager.postprocess_record

        if postprocess_record:
            try:
                postprocess_record(pk, sk, old_item, new_item)
            except Exception as err:
                logger.exception(str(err))
