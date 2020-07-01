import logging

from boto3.dynamodb.types import TypeDeserializer

from app import clients, models
from app.logging import LogLevelContext, handler_logging

from . import xray

logger = logging.getLogger()
xray.patch_all()

clients = {
    'appsync': clients.AppSyncClient(),
    'dynamo': clients.DynamoClient(),
    'elasticsearch': clients.ElasticSearchClient(),
    'pinpoint': clients.PinpointClient(),
}

managers = {}
card_manager = managers.get('card') or models.CardManager(clients, managers=managers)
chat_manager = managers.get('chat') or models.ChatManager(clients, managers=managers)
chat_message_manager = managers.get('chat_message') or models.ChatMessageManager(clients, managers=managers)
comment_manager = managers.get('comment') or models.CommentManager(clients, managers=managers)
follower_manager = managers.get('follower') or models.FollowerManager(clients, managers=managers)
post_manager = managers.get('post') or models.PostManager(clients, managers=managers)
user_manager = managers.get('user') or models.UserManager(clients, managers=managers)

# https://stackoverflow.com/a/46738251
deserialize = TypeDeserializer().deserialize


@handler_logging
def postprocess_records(event, context):
    for record in event['Records']:

        pk = deserialize(record['dynamodb']['Keys']['partitionKey'])
        sk = deserialize(record['dynamodb']['Keys']['sortKey'])
        old_item = {k: deserialize(v) for k, v in record['dynamodb'].get('OldImage', {}).items()}
        new_item = {k: deserialize(v) for k, v in record['dynamodb'].get('NewImage', {}).items()}

        op = 'edit' if old_item and new_item else 'add' if not old_item else 'delete' if not new_item else 'unkn'
        with LogLevelContext(logger, logging.INFO):
            logger.info(f'Post-processing `{op}` operation of record `{pk}`, `{sk}`')

        postprocessor = None

        if pk.startswith('card/'):
            postprocessor = card_manager.postprocessor

        if pk.startswith('chat/'):
            postprocessor = chat_manager.postprocessor

        if pk.startswith('chatMessage/'):
            postprocessor = chat_message_manager.postprocessor

        if pk.startswith('comment/'):
            postprocessor = comment_manager.postprocessor

        if pk.startswith('post/'):
            postprocessor = post_manager.postprocessor

        if pk.startswith('user/') and sk.startswith('follower/'):
            postprocessor = follower_manager.postprocessor

        if pk.startswith('user/') and sk == 'profile':
            postprocessor = user_manager.postprocessor

        if postprocessor:
            try:
                postprocessor.run(pk, sk, old_item, new_item)
            except Exception as err:
                logger.exception(str(err))
