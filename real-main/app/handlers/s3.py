import logging
import os
import urllib

from app.clients import CloudFrontClient, DynamoClient, S3Client, SecretsManagerClient
from app.logging import LogLevelContext
from app.models.media import MediaManager
from app.models.media.enums import MediaStatus
from app.models.post import PostManager
from app.utils import image_size

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

    try:
        user_id, post_id, media_id, media_size, media_ext = media_manager.parse_s3_path(path)
    except ValueError:
        # not a media path
        return

    if media_size != image_size.NATIVE.name:
        # this was a thumbnail
        return

    # strongly consistent because we may have just added the pending post
    media = media_manager.get_media(media_id, strongly_consistent=True)
    if not media:
        raise Exception(f'Unable to find media `{media_id}` for post `{post_id}`')

    media_status = media.item['mediaStatus']
    if media_status not in (MediaStatus.AWAITING_UPLOAD, MediaStatus.ERROR):
        # this media upload was already processed. Direct image data upload?
        return

    # strongly consistent because we may have just added the pending post
    post = post_manager.get_post(post_id, strongly_consistent=True)

    try:
        media.process_upload()
    except media.exceptions.MediaException as err:
        logger.warning(str(err))
        post.error()

    # if the post in in error state (from this media or other media) then we are done
    if post.item['postStatus'] == post.enums.PostStatus.ERROR:
        return

    # is there other media left to upload? if not, complete the post
    for media in media_manager.dynamo.generate_by_post(post_id, uploaded=False):
        if media['mediaId'] != media_id:
            return
    post.complete()
