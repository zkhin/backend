import logging

from app import clients, models
from app.logging import LogLevelContext, handler_logging
from app.models.chat_message.enums import ChatMessageNotificationType

from . import xray

logger = logging.getLogger()
xray.patch_all()

clients = {
    'appsync': clients.AppSyncClient(),
    'dynamo': clients.DynamoClient(),
    'cognito': clients.CognitoClient(),
    'pinpoint': clients.PinpointClient(),
}

managers = {}
chat_manager = managers.get('chat') or models.ChatManager(clients, managers=managers)
chat_message_manager = managers.get('chat_message') or models.ChatMessageManager(clients, managers=managers)
user_manager = managers.get('user') or models.UserManager(clients, managers=managers)


@handler_logging(event_to_extras=lambda event: {'event': event})
def create_dating_chat(event, context):
    with LogLevelContext(logger, logging.INFO):
        logger.info('create_dating_chat() called')

    user_id = event['userId']
    chat_id, user_ids, name = event['chatId'], event['userIds'], event.get('name')
    message_id, message_text = event['messageId'], event['messageText']

    caller_user = user_manager.get_user(user_id)
    chat = chat_manager.add_group_chat(chat_id, caller_user, name=name)
    chat.add(caller_user, user_ids)
    message = chat_message_manager.add_chat_message(message_id, message_text, chat_id, user_id)

    message.trigger_notifications(ChatMessageNotificationType.ADDED, user_ids=user_ids)
    chat.refresh_item(strongly_consistent=True)
    return chat.item
