import logging

from boto3.dynamodb.types import TypeDeserializer

from app import clients, models
from app.handlers import xray
from app.logging import LogLevelContext, handler_logging
from app.models.user.enums import UserStatus

from .dispatch import AttributeDispatch, ItemDispatch, attrs

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


on_attribute_change_dispatch = AttributeDispatch(
    {
        'post': {
            '-': {
                post_manager.sync_comments_card: attrs(commentsUnviewedCount=0),
                # DISABLED until frontend implements or at least ignores
                # post_manager.sync_post_likes_card: attrs(anonymousLikeCount=0, onymousLikeCount=0),
                # post_manager.sync_post_views_card: attrs(viewedByCount=0),
            }
        },
        'user': {
            'profile': {
                user_manager.sync_user_status_due_to_chat_messages: attrs(chatMessagesForcedDeletionCount=0),
                user_manager.sync_user_status_due_to_comments: attrs(commentForcedDeletionCount=0),
                user_manager.sync_user_status_due_to_posts: attrs(postForcedArchivingCount=0),
                user_manager.sync_requested_followers_card: attrs(followersRequestedCount=0),
                user_manager.sync_chats_with_new_messages_card: attrs(chatsWithUnviewedMessagesCount=0),
                user_manager.sync_pinpoint_email: attrs(email=None),
                user_manager.sync_pinpoint_phone: attrs(phoneNumber=None),
                user_manager.sync_pinpoint_user_status: attrs(userStatus=UserStatus.ACTIVE),
                user_manager.sync_elasticsearch: attrs(
                    username=None, fullName=None, lastManuallyReindexedAt=None
                ),
            }
        },
    }
)

on_item_add_dispatch = ItemDispatch(
    {
        'comment': {'-': (user_manager.on_comment_add,)},
        'like': {'-': (post_manager.on_like_add,)},  # old, deprecated like pk format
        'post': {'like': (post_manager.on_like_add,), 'view': (post_manager.on_view_add,)},
    }
)
on_item_delete_dispatch = ItemDispatch(
    {
        'like': {'-': (post_manager.on_like_delete,)},  # old, deprecated like pk format
        'comment': {'-': (user_manager.on_comment_delete,)},
        'post': {'-': (post_manager.on_delete,), 'like': (post_manager.on_like_delete,)},
        'user': {'profile': (card_manager.on_user_delete, user_manager.on_user_delete)},
    }
)


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

        # fire item add listeners
        if name == 'INSERT':
            for func in on_item_add_dispatch.search(pk_prefix, sk_prefix):
                with LogLevelContext(logger, logging.INFO):
                    logger.info(f'{name}: `{pk}` / `{sk}` running item add: {func}')
                try:
                    func(item_id, new_item)
                except Exception as err:
                    logger.exception(str(err))

        # fire attribute change listeners
        if name == 'INSERT' or name == 'MODIFY':
            for func in on_attribute_change_dispatch.search(pk_prefix, sk_prefix, old_item, new_item):
                with LogLevelContext(logger, logging.INFO):
                    logger.info(f'{name}: `{pk}` / `{sk}` running attribute change: {func}')
                try:
                    func(item_id, old_item, new_item)
                except Exception as err:
                    logger.exception(str(err))

        # fire item delete listeners
        if name == 'REMOVE':
            for func in on_item_delete_dispatch.search(pk_prefix, sk_prefix):
                with LogLevelContext(logger, logging.INFO):
                    logger.info(f'{name}: `{pk}` / `{sk}` running item delete: {func}')
                try:
                    func(item_id, old_item)
                except Exception as err:
                    logger.exception(str(err))
