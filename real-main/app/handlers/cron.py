import logging
import os

import pendulum

from app import clients, models
from app.logging import LogLevelContext, handler_logging

from . import xray

S3_UPLOADS_BUCKET = os.environ.get('S3_UPLOADS_BUCKET')
USER_NOTIFICATIONS_ENABLED = os.environ.get('USER_NOTIFICATIONS_ENABLED')

logger = logging.getLogger()
xray.patch_all()

cognito_client = clients.CognitoClient()
dynamo_client = clients.DynamoClient()
s3_uploads_client = clients.S3Client(S3_UPLOADS_BUCKET)
clients = {
    'dynamo': dynamo_client,
    'cognito': cognito_client,
    's3_uploads': s3_uploads_client,
}

managers = {}
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
    now = pendulum.now('utc')
    total_cnt, success_cnt = card_manager.notify_users(now=now)
    with LogLevelContext(logger, logging.INFO):
        logger.info(f'User notifications sent successfully: {success_cnt} out of {total_cnt}')
