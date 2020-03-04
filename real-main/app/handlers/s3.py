import logging
import os
import urllib

from app.clients import CloudFrontClient, DynamoClient, S3Client, SecretsManagerClient
from app.logging import LogLevelContext
from app.models.media import MediaManager
from app.models.post import PostManager
from app.models.post.enums import PostStatus

UPLOADS_BUCKET = os.environ.get('UPLOADS_BUCKET')

logger = logging.getLogger()

secrets_manager_client = SecretsManagerClient()
clients = {
    'cloudfront': CloudFrontClient(secrets_manager_client.get_cloudfront_key_pair),
    'dynamo': DynamoClient(),
    's3_uploads': S3Client(UPLOADS_BUCKET),
    'secrets_manager': secrets_manager_client,
}

managers = {}
media_manager = managers.get('media') or MediaManager(clients, managers=managers)
post_manager = managers.get('post') or PostManager(clients, managers=managers)


def uploads_object_created(event, context):
    # Seems the boto s3 client deals with non-urlencoded keys to objects everywhere, but
    # apparenttly this falls outside that scope. The event emitter passes us a urlencoded path.
    path = urllib.parse.unquote(event['Records'][0]['s3']['object']['key'])

    # we suppress INFO logging, except this message
    with LogLevelContext(logger, logging.INFO):
        logger.info(f'BEGIN: Handling object created event for key `{path}`')

    elems = post_manager.parse_s3_path(path)
    if not elems:
        # not a native-size image path
        return
    post_id = elems['post_id']
    media_id = elems.get('media_id')

    # strongly consistent because we may have just added the post to dynamo
    post = post_manager.get_post(post_id, strongly_consistent=True)
    if not post:
        logger.warning(f'Unable to find post `{post_id}`, ignoring upload')
        return

    if post.post_status != PostStatus.PENDING:
        logger.warning(f'Post `{post_id}` is not in PENDING status: `{post.post_status}`, ignoring upload')
        return

    # strongly consistent because we may have just added the media to dynamo
    media = media_manager.get_media(media_id, strongly_consistent=True) if media_id else None
    if media_id and not media:
        logger.warning(f'Unable to find media `{media_id}`, ignoring upload')
        return

    try:
        post.process_image_upload(media=media)
    except (post.exceptions.PostException, media.exceptions.MediaException) as err:
        logger.warning(str(err))
        post.error(media=media)
