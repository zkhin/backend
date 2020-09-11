import logging
import os

import pendulum

from app import clients, models
from app.logging import LogLevelContext, handler_logging

from . import xray

S3_UPLOADS_BUCKET = os.environ.get('S3_UPLOADS_BUCKET')
USER_NOTIFICATIONS_ENABLED = os.environ.get('USER_NOTIFICATIONS_ENABLED')
USER_NOTIFICATIONS_ONLY_USERNAMES = os.environ.get('USER_NOTIFICATIONS_ONLY_USERNAMES')

logger = logging.getLogger()
xray.patch_all()

clients = {
    'appstore': clients.AppStoreClient(),
    'dynamo': clients.DynamoClient(),
    'cognito': clients.CognitoClient(),
    'pinpoint': clients.PinpointClient(),
    's3_uploads': clients.S3Client(S3_UPLOADS_BUCKET),
}

managers = {}
appstore_manager = managers.get('appstore') or models.AppStoreManager(clients, managers=managers)
album_manager = managers.get('album') or models.AlbumManager(clients, managers=managers)
card_manager = managers.get('card') or models.CardManager(clients, managers=managers)
post_manager = managers.get('post') or models.PostManager(clients, managers=managers)
user_manager = managers.get('user') or models.UserManager(clients, managers=managers)


@handler_logging
def deflate_trending_users(event, context):
    total_cnt, deflated_cnt = user_manager.trending_deflate()
    with LogLevelContext(logger, logging.INFO):
        logger.info(f'Trending users deflated: {deflated_cnt} out of {total_cnt}')
    deleted_cnt = user_manager.trending_delete_tail(total_cnt)
    with LogLevelContext(logger, logging.INFO):
        logger.info(f'Trending users removed: {deleted_cnt} out of {total_cnt}')


@handler_logging
def deflate_trending_posts(event, context):
    total_cnt, deflated_cnt = post_manager.trending_deflate()
    with LogLevelContext(logger, logging.INFO):
        logger.info(f'Trending posts deflated: {deflated_cnt} out of {total_cnt}')
    deleted_cnt = post_manager.trending_delete_tail(total_cnt)
    with LogLevelContext(logger, logging.INFO):
        logger.info(f'Trending posts removed: {deleted_cnt} out of {total_cnt}')


@handler_logging
def update_appstore_subscriptions(event, context):
    cnt = appstore_manager.update_subscriptions()
    with LogLevelContext(logger, logging.INFO):
        logger.info(f'AppStore subscriptions updated: {cnt}')


@handler_logging
def garbage_collect_albums(event, context):
    cnt = album_manager.garbage_collect()
    with LogLevelContext(logger, logging.INFO):
        logger.info(f'Albums garbage collected: {cnt}')


@handler_logging
def delete_recently_expired_posts(event, context):
    now = pendulum.now('utc')
    post_manager.delete_recently_expired_posts(now=now)


@handler_logging
def delete_older_expired_posts(event, context):
    now = pendulum.now('utc')
    post_manager.delete_older_expired_posts(now=now)


@handler_logging
def send_user_notifications(event, context):
    if not USER_NOTIFICATIONS_ENABLED:
        with LogLevelContext(logger, logging.INFO):
            logger.info('User notifications disabled')
        return
    only_usernames = USER_NOTIFICATIONS_ONLY_USERNAMES.split(' ') if USER_NOTIFICATIONS_ONLY_USERNAMES else None
    with LogLevelContext(logger, logging.INFO):
        logger.info(f'Preparing to send notifications as needed to users: {only_usernames or "all"}')
    now = pendulum.now('utc')
    total_cnt, success_cnt = card_manager.notify_users(now=now, only_usernames=only_usernames)
    with LogLevelContext(logger, logging.INFO):
        logger.info(f'User notifications sent successfully: {success_cnt} out of {total_cnt}')


@handler_logging
def clear_expired_user_subscriptions(event, context):
    cnt = user_manager.clear_expired_subscriptions()
    with LogLevelContext(logger, logging.INFO):
        logger.info(f'Expired user subscriptions cleared: {cnt}')


# TODO: enable to handle re-verification of apple receipts after temporary failures
# @handler_logging
# def verify_receipts(event, context):
#     now = pendulum.now('utc')
#     total_cnt, success_cnt = apple_receipt_manager.verify_receipts(now=now)
#     with LogLevelContext(logger, logging.INFO):
#         logger.info(f'Apple receipts verified: {success_cnt} out of {total_cnt}')
