import logging

from . import enums, exceptions
from .dynamo import MediaDynamo
from .model import Media

logger = logging.getLogger()


class MediaManager:

    enums = enums
    exceptions = exceptions

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['media'] = self

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = MediaDynamo(clients['dynamo'])

    def parse_s3_path(self, path):
        user_id, sep1, post_id, sep2, media_id, filename = path.split('/')
        if sep1 != 'post' or sep2 != 'media':
            raise ValueError('Not a media path')
        media_size, media_ext = filename.split('.')
        return user_id, post_id, media_id, media_size, media_ext

    def get_media(self, media_id):
        "Pull media item from dynamo, initialize a new Media instance with it"
        media_item = self.dynamo.get_media(media_id)
        if not media_item:
            return None
        return Media(media_item, self.clients)

    def init_media(self, media_item):
        "Use the provided media item to initialize a new Media instance"
        return Media(media_item, self.clients)
