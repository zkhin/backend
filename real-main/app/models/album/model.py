import logging

from . import exceptions
from .dynamo import AlbumDynamo

logger = logging.getLogger()


class Album:

    exceptions = exceptions

    def __init__(self, album_item, clients, user_manager=None, post_manager=None):
        self.clients = clients
        if 'dynamo' in clients:
            self.dynamo = AlbumDynamo(clients['dynamo'])
        if post_manager:
            self.post_manager = post_manager
        if user_manager:
            self.user_manager = user_manager
        self.id = album_item['albumId']
        self.item = album_item

    def refresh_item(self, strongly_consistent=False):
        self.item = self.dynamo.get_album(self.id, strongly_consistent=strongly_consistent)
        return self

    def serialize(self, caller_user_id):
        resp = self.item.copy()
        user = self.user_manager.get_user(resp['ownedByUserId'])
        resp['ownedBy'] = user.serialize(caller_user_id)
        return resp

    def update(self, name=None, description=None):
        if name == '':
            raise exceptions.AlbumException('All posts must have names')
        self.item = self.dynamo.set(self.id, name=name, description=description)
        return self

    def delete(self):
        # remove all the posts from this album
        for post_id in self.post_manager.dynamo.generate_post_ids_in_album(self.id):
            post = self.post_manager.get_post(post_id)
            post.set_album(None)

        # order matters to moto (in test suite), but not on dynamo
        transacts = [
            self.user_manager.dynamo.transact_decrement_album_count(self.item['ownedByUserId']),
            self.dynamo.transact_delete_album(self.id),
        ]
        transact_exceptions = [
            exceptions.AlbumException(f'Unable to decrement album count for user `{self.item["ownedByUserId"]}`'),
            exceptions.AlbumException(f'Album `{self.id}` does not exist'),
        ]
        self.dynamo.client.transact_write_items(transacts, transact_exceptions)
        return self
