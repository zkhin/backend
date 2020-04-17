import logging

from . import exceptions
from .dynamo import MediaDynamo
from .model import Media

logger = logging.getLogger()


class MediaManager:

    exceptions = exceptions

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['media'] = self

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = MediaDynamo(clients['dynamo'])

    def get_media(self, media_id, strongly_consistent=False):
        "Pull media item from dynamo, initialize a new Media instance with it"
        media_item = self.dynamo.get_media(media_id, strongly_consistent=strongly_consistent)
        if not media_item:
            return None
        return self.init_media(media_item)

    def init_media(self, media_item):
        "Use the provided media item to initialize a new Media instance"
        kwargs = {
            'cloudfront_client': self.clients.get('cloudfront'),
            'post_verification_client': self.clients.get('post_verification'),
            's3_uploads_client': self.clients.get('s3_uploads'),
        }
        return Media(media_item, self.dynamo, **kwargs)
