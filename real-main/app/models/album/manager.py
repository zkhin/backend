import logging

import pendulum

from app import models

from .dynamo import AlbumDynamo
from .model import Album

logger = logging.getLogger()


class AlbumManager:
    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['album'] = self
        self.post_manager = managers.get('post') or models.PostManager(clients, managers=managers)
        self.user_manager = managers.get('user') or models.UserManager(clients, managers=managers)

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = AlbumDynamo(clients['dynamo'])

    def get_album(self, album_id):
        album_item = self.dynamo.get_album(album_id)
        return self.init_album(album_item) if album_item else None

    def init_album(self, album_item):
        return Album(
            album_item,
            self.dynamo,
            s3_uploads_client=self.clients.get('s3_uploads'),
            cloudfront_client=self.clients.get('cloudfront'),
            user_manager=self.user_manager,
            post_manager=self.post_manager,
        )

    def add_album(self, caller_user_id, album_id, name, description=None, now=None):
        now = now or pendulum.now('utc')
        description = None if description == '' else description  # treat empty string as null
        album_item = self.dynamo.add_album(album_id, caller_user_id, name, description, created_at=now)
        return self.init_album(album_item)

    def delete_all_by_user(self, user_id):
        for album_item in self.dynamo.generate_by_user(user_id):
            self.init_album(album_item).delete()
