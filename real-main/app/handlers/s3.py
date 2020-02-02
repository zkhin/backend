import logging
import os
import urllib

from app.clients import CloudFrontClient, DynamoClient, S3Client, SecretsManagerClient
from app.models.media import MediaManager
from app.models.media.enums import MediaStatus, MediaType, MediaSize
from app.models.post import PostManager

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
    try:
        user_id, post_id, media_id, media_size, media_ext = media_manager.parse_s3_path(path)
    except ValueError:
        # not a media path
        return

    if media_size != MediaSize.NATIVE:
        # this was a thumbnail
        return

    media = media_manager.get_media(media_id)
    if not media:
        raise Exception(f'Unable to find non-uploaded media `{media_id}` for post `{post_id}`')

    media_status = media.item['mediaStatus']
    if media_status in (MediaStatus.ARCHIVED, MediaStatus.DELETING):
        raise Exception(f'Refusing to process media upload for media `{media_id}` with status `{media_status}`')

    media.set_status(MediaStatus.PROCESSING_UPLOAD)

    # if this an image, compute and save its dimensions
    if media.item['mediaType'] == MediaType.IMAGE:

        # only accept jpeg uploads
        if not media.is_original_jpeg():
            logger.warning(f'Non-jpeg image uploaded for media `{media_id}`')
            media.set_status(MediaStatus.ERROR)
            return

        media.set_is_verified()
        media.set_height_and_width()
        media.set_thumbnails()
        media.set_checksum()

    media.set_status(MediaStatus.UPLOADED)

    # is there other media left to upload?
    for media in media_manager.dynamo.generate_by_post(post_id, uploaded=False):
        if media['mediaId'] != media_id:
            return

    # this was the last media for the post, so mark it complete
    post_manager.get_post(post_id).complete()
