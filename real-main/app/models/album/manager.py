import logging

import pendulum

from app.models import media, post, user

from . import exceptions
from .dynamo import AlbumDynamo
from .model import Album

logger = logging.getLogger()


class AlbumManager:

    exceptions = exceptions

    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['album'] = self
        self.media_manager = managers.get('media') or media.MediaManager(clients, managers=managers)
        self.post_manager = managers.get('post') or post.PostManager(clients, managers=managers)
        self.user_manager = managers.get('user') or user.UserManager(clients, managers=managers)

        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = AlbumDynamo(clients['dynamo'])

    def get_album(self, album_id):
        album_item = self.dynamo.get_album(album_id)
        return self.init_album(album_item) if album_item else None

    def init_album(self, album_item):
        return Album(album_item, self.dynamo, s3_uploads_client=self.clients.get('s3_uploads'),
                     cloudfront_client=self.clients.get('cloudfront'), user_manager=self.user_manager,
                     post_manager=self.post_manager, media_manager=self.media_manager)

    def add_album(self, caller_user_id, album_id, name, description=None, now=None):
        now = now or pendulum.now('utc')
        description = None if description == '' else description  # treat empty string as null

        # test suite cares about order here, but it doesn't actually matter
        transacts = [
            self.user_manager.dynamo.transact_increment_album_count(caller_user_id),
            self.dynamo.transact_add_album(album_id, caller_user_id, name, description, created_at=now),
        ]
        transact_exceptions = [
            exceptions.AlbumException('Unable to increment User.albumCount'),
            exceptions.AlbumException(f'Unable to add album with id `{album_id}`... id already used?'),
        ]
        self.dynamo.client.transact_write_items(transacts, transact_exceptions)

        album_item = self.dynamo.get_album(album_id, strongly_consistent=True)
        return self.init_album(album_item)

    def delete_all_by_user(self, user_id):
        for album_item in self.dynamo.generate_by_user(user_id):
            self.init_album(album_item).delete()
