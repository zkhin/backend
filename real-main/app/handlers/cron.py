import logging
import os

import pendulum

from app.clients import CognitoClient, DynamoClient, S3Client
from app.models.post import PostManager
from app.models.trending import TrendingManager

UPLOADS_BUCKET = os.environ.get('UPLOADS_BUCKET')

logger = logging.getLogger()

cognito_client = CognitoClient()
dynamo_client = DynamoClient()
s3_uploads_client = S3Client(UPLOADS_BUCKET)
clients = {
    'dynamo': dynamo_client,
    'cognito': cognito_client,
    's3_uploads': s3_uploads_client,
}

managers = {}
post_manager = managers.get('post') or PostManager(clients, managers=managers)
trending_manager = managers.get('trending') or TrendingManager(clients, managers=managers)


def reindex_trending_users(event, context):
    now = pendulum.now('utc')
    trending_manager.reindex(trending_manager.enums.TrendingItemType.USER, cutoff=now)


def reindex_trending_posts(event, context):
    now = pendulum.now('utc')
    trending_manager.reindex(trending_manager.enums.TrendingItemType.POST, cutoff=now)


def delete_recently_expired_posts(event, context):
    now = pendulum.now('utc')
    post_manager.delete_recently_expired_posts(now=now)


def delete_older_expired_posts(event, context):
    now = pendulum.now('utc')
    post_manager.delete_older_expired_posts(now=now)


def delete_unconfirmed_expired_users_in_cognito(event, context):
    """
    Delete all unconfirmed users in the cognito user and identity pools for which their confirmation code
    has expired.
    """
    now = pendulum.now('utc')
    # confirmation code lasts 24 hours
    # https://docs.aws.amazon.com/cognito/latest/developerguide/limits.html#limits-hard
    lifetime = pendulum.duration(hours=24)
    cutoff = now - lifetime

    # iterate over unconfirmed entries in the user pool
    for item in cognito_client.list_unconfirmed_users_pool_entries():
        last_modified_at = pendulum.instance(item['UserLastModifiedDate']).in_tz('utc')
        if last_modified_at > cutoff:
            continue
        user_id = item['Username']

        # do another request to be absolutely sure this user is unconfirmed before we delete them
        user_status = cognito_client.get_user_status(user_id)
        if user_status != 'UNCONFIRMED':
            logger.error(f'Cognito user pool entry changed from UNCONFIRMED to `{user_status}`, not deleting')
            continue

        # delete them
        msg = f'Deleting user pool entry for unconfirmed user `{user_id}`'
        if 'email' in item:
            msg += f' with email `{item["email"]}`'
        if 'phone_number' in item:
            msg += f' with phone number `{item["phone_number"]}`'
        logger.warning(msg)
        cognito_client.delete_user_pool_entry(user_id)
