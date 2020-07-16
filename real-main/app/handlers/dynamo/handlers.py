import logging

from boto3.dynamodb.types import TypeDeserializer

from app import clients, models
from app.handlers import xray
from app.logging import LogLevelContext, handler_logging
from app.models.user.enums import UserStatus

from .dispatch import DynamoDispatch

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

dispatch = DynamoDispatch()
register = dispatch.register

register('card', '-', ['INSERT'], card_manager.on_card_add)
register('card', '-', ['INSERT'], user_manager.on_card_add)
register('card', '-', ['MODIFY'], card_manager.on_card_edit)
register('card', '-', ['REMOVE'], card_manager.on_card_delete)
register('card', '-', ['REMOVE'], user_manager.on_card_delete)
register(
    'chat',
    'member',
    ['INSERT', 'MODIFY', 'REMOVE'],
    user_manager.sync_chats_with_unviewed_messages_count,
    {'messagesUnviewedCount': 0},
)
register('chat', 'view', ['INSERT', 'MODIFY'], chat_manager.sync_member_messages_unviewed_count, {'viewCount': 0})
register('chatMessage', 'flag', ['INSERT'], chat_message_manager.on_flag_add)
register('chatMessage', 'flag', ['REMOVE'], chat_message_manager.on_flag_delete)
register('comment', '-', ['INSERT'], post_manager.on_comment_add)
register('comment', '-', ['INSERT'], user_manager.on_comment_add)
register('comment', '-', ['REMOVE'], post_manager.on_comment_delete)
register('comment', '-', ['REMOVE'], user_manager.on_comment_delete)
register('comment', 'flag', ['INSERT'], comment_manager.on_flag_add)
register('comment', 'flag', ['REMOVE'], comment_manager.on_flag_delete)
register('like', '-', ['INSERT'], post_manager.on_like_add)  # old, deprecated like pk format
register('like', '-', ['REMOVE'], post_manager.on_like_delete)  # old, deprecated like pk format
register('post', '-', ['INSERT', 'MODIFY'], post_manager.sync_comments_card, {'commentsUnviewedCount': 0})
register('post', '-', ['REMOVE'], post_manager.on_delete)
register('post', 'flag', ['INSERT'], post_manager.on_flag_add)
register('post', 'flag', ['REMOVE'], post_manager.on_flag_delete)
register('post', 'like', ['INSERT'], post_manager.on_like_add)
register('post', 'like', ['REMOVE'], post_manager.on_like_delete)
register('post', 'view', ['INSERT'], post_manager.on_view_add)
# DISABLED until frontend implements or at least ignores
# register(
#     'post',
#     '-',
#     ['INSERT', 'MODIFY'],
#     post_manager.sync_post_likes_card,
#     {'anonymousLikeCount': 0, 'onymousLikeCount': 0},
# )
# register('post', '-', ['INSERT', 'MODIFY'], post_manager.sync_post_views_card, {'viewedByCount': 0})
register(
    'user',
    'profile',
    ['INSERT', 'MODIFY'],
    user_manager.sync_user_status_due_to_chat_messages,
    {'chatMessagesForcedDeletionCount': 0},
)
register(
    'user',
    'profile',
    ['INSERT', 'MODIFY'],
    user_manager.sync_user_status_due_to_comments,
    {'commentForcedDeletionCount': 0},
)
register(
    'user',
    'profile',
    ['INSERT', 'MODIFY'],
    user_manager.sync_user_status_due_to_posts,
    {'postForcedArchivingCount': 0},
)
register(
    'user',
    'profile',
    ['INSERT', 'MODIFY'],
    user_manager.sync_requested_followers_card,
    {'followersRequestedCount': 0},
)
register(
    'user',
    'profile',
    ['INSERT', 'MODIFY'],
    user_manager.sync_chats_with_new_messages_card,
    {'chatsWithUnviewedMessagesCount': 0},
)
register(
    'user',
    'profile',
    ['INSERT', 'MODIFY'],
    user_manager.fire_gql_subscription_chats_with_unviewed_messages_count,
    {'chatsWithUnviewedMessagesCount': 0},
)
register('user', 'profile', ['INSERT', 'MODIFY'], user_manager.sync_pinpoint_email, {'email': None})
register('user', 'profile', ['INSERT', 'MODIFY'], user_manager.sync_pinpoint_phone, {'phoneNumber': None})
register(
    'user',
    'profile',
    ['INSERT', 'MODIFY'],
    user_manager.sync_pinpoint_user_status,
    {'userStatus': UserStatus.ACTIVE},
)
register(
    'user',
    'profile',
    ['INSERT', 'MODIFY'],
    user_manager.sync_elasticsearch,
    {'username': None, 'fullName': None, 'lastManuallyReindexedAt': None},
)
register('user', 'profile', ['REMOVE'], card_manager.on_user_delete)
register('user', 'profile', ['REMOVE'], user_manager.on_user_delete)


@handler_logging
def process_records(event, context):
    for record in event['Records']:

        name = record['eventName']
        pk = deserialize(record['dynamodb']['Keys']['partitionKey'])
        sk = deserialize(record['dynamodb']['Keys']['sortKey'])
        old_item = {k: deserialize(v) for k, v in record['dynamodb'].get('OldImage', {}).items()}
        new_item = {k: deserialize(v) for k, v in record['dynamodb'].get('NewImage', {}).items()}

        with LogLevelContext(logger, logging.INFO):
            logger.info(f'{name}: `{pk}` / `{sk}` starting processing')

        # legacy postprocessors
        postprocessor = None

        if pk.startswith('chatMessage/'):
            postprocessor = chat_message_manager.postprocessor

        if pk.startswith('user/') and sk.startswith('follower/'):
            postprocessor = follower_manager.postprocessor

        if postprocessor:
            with LogLevelContext(logger, logging.INFO):
                logger.info(f'{name}: `{pk}` / `{sk}` running postprocessor: {postprocessor.run}')
            try:
                postprocessor.run(pk, sk, old_item, new_item)
            except Exception as err:
                logger.exception(str(err))

        # we still have some pks in an old (& deprecated) format with more than one item_id in the pk
        pk_prefix, item_id = pk.split('/')[:2]
        sk_prefix = sk.split('/')[0]

        item_kwargs = {k: v for k, v in {'new_item': new_item, 'old_item': old_item}.items() if v}
        for func in dispatch.search(pk_prefix, sk_prefix, name, old_item, new_item):
            with LogLevelContext(logger, logging.INFO):
                logger.info(f'{name}: `{pk}` / `{sk}` running: {func}')
            try:
                func(item_id, **item_kwargs)
            except Exception as err:
                logger.exception(str(err))
