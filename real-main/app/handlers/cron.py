import logging
import os

import pendulum

from app import clients, models
from app.logging import handler_logging

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
def delete_recently_expired_posts(event, context):
    now = pendulum.now('utc')
    post_manager.delete_recently_expired_posts(now=now)


@handler_logging
def delete_older_expired_posts(event, context):
    now = pendulum.now('utc')
    post_manager.delete_older_expired_posts(now=now)
