import logging

import pendulum

from app import models

from .dynamo import AlbumDynamo
from .model import Album

logger = logging.getLogger()


class AlbumManager:

    zero_post_lifetime = pendulum.duration(hours=24)

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

    def garbage_collect(self, now=None):
        now = now or pendulum.now('utc')
        generator = self.dynamo.generate_keys_to_delete(now)
        return self.dynamo.client.batch_delete_items(generator)

    def on_album_delete_delete_album_art(self, album_id, old_item):
        if art_hash := old_item.get('artHash'):
            album = self.init_album(old_item)
            album.delete_art_images(art_hash)

    def on_album_add_edit_sync_delete_at(self, album_id, new_item, old_item=None):
        new_count = new_item.get('postCount', 0)
        if new_count == 0 and 'gsiK1PartitionKey' not in new_item:
            self.dynamo.set_delete_at_fail_soft(album_id, pendulum.now('utc') + self.zero_post_lifetime)
        if new_count > 0 and 'gsiK1PartitionKey' in new_item:
            self.dynamo.clear_delete_at_fail_soft(album_id)
