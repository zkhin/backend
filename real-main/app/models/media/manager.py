import logging

from .dynamo import MediaDynamo
from .model import Media

logger = logging.getLogger()


class MediaManager:

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['media'] = self
        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = MediaDynamo(clients['dynamo'])

    def get_media(self, media_id, strongly_consistent=False):
        "Pull media item from dynamo, initialize a new Media instance with it"
        media_item = self.dynamo.get_media(media_id, strongly_consistent=strongly_consistent)
        return self.init_media(media_item) if media_item else None

    def init_media(self, media_item):
        "Use the provided media item to initialize a new Media instance"
        return Media(media_item, self.dynamo)
