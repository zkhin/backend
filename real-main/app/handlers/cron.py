import logging
import os

import pendulum

from app import clients, models
from app.logging import LogLevelContext, handler_logging

from . import xray

S3_UPLOADS_BUCKET = os.environ.get('S3_UPLOADS_BUCKET')

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
user_manager = managers.get('user') or models.UserManager(clients, managers=managers)
post_manager = managers.get('post') or models.PostManager(clients, managers=managers)
trending_manager = managers.get('trending') or models.TrendingManager(clients, managers=managers)


@handler_logging
def reindex_trending_users(event, context):
    now = pendulum.now('utc')
    trending_manager.reindex(trending_manager.enums.TrendingItemType.USER, cutoff=now)


@handler_logging
def reindex_trending_posts(event, context):
    now = pendulum.now('utc')
    trending_manager.reindex(trending_manager.enums.TrendingItemType.POST, cutoff=now)


@handler_logging
def deflate_trending_users(event, context):
    deflated_cnt = user_manager.trending_deflate()
    with LogLevelContext(logger, logging.INFO):
        logger.info('Trending users deflated: `{deflated_cnt}`')
    deleted_cnt = user_manager.trending_delete_tail(deflated_cnt)
    with LogLevelContext(logger, logging.INFO):
        logger.info(f'Trending users deleted: `{deleted_cnt}`')


@handler_logging
def deflate_trending_posts(event, context):
    deflated_cnt = post_manager.trending_deflate()
    with LogLevelContext(logger, logging.INFO):
        logger.info(f'Trending posts deflated: `{deflated_cnt}`')
    deleted_cnt = post_manager.trending_delete_tail(deflated_cnt)
    with LogLevelContext(logger, logging.INFO):
        logger.info(f'Trending posts deleted: `{deleted_cnt}`')


@handler_logging
def delete_recently_expired_posts(event, context):
    now = pendulum.now('utc')
    post_manager.delete_recently_expired_posts(now=now)


@handler_logging
def delete_older_expired_posts(event, context):
    now = pendulum.now('utc')
    post_manager.delete_older_expired_posts(now=now)
