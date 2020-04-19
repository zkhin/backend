import hashlib
from io import BytesIO
import itertools
import logging
import os

from PIL import Image

from app.utils import image_size

from . import art, exceptions

logger = logging.getLogger()

CLOUDFRONT_FRONTEND_RESOURCES_DOMAIN = os.environ.get('CLOUDFRONT_FRONTEND_RESOURCES_DOMAIN')


class Album:

    exceptions = exceptions
    jpeg_content_type = 'image/jpeg'

    def __init__(self, album_item, album_dynamo, cloudfront_client=None, s3_uploads_client=None,
                 user_manager=None, post_manager=None,
                 frontend_resources_domain=CLOUDFRONT_FRONTEND_RESOURCES_DOMAIN):
        self.dynamo = album_dynamo
        if cloudfront_client:
            self.cloudfront_client = cloudfront_client
        if s3_uploads_client:
            self.s3_uploads_client = s3_uploads_client
        if post_manager:
            self.post_manager = post_manager
        if user_manager:
            self.user_manager = user_manager
        self.frontend_resources_domain = frontend_resources_domain
        self.item = album_item
        self.id = album_item['albumId']
        self.user_id = album_item['ownedByUserId']

    def refresh_item(self, strongly_consistent=False):
        self.item = self.dynamo.get_album(self.id, strongly_consistent=strongly_consistent)
        return self

    def serialize(self, caller_user_id):
        resp = self.item.copy()
        resp['ownedBy'] = self.user_manager.get_user(self.user_id).serialize(caller_user_id)
        return resp

    def update(self, name=None, description=None):
        if name == '':
            raise exceptions.AlbumException('All albums must have names')
        self.item = self.dynamo.set(self.id, name=name, description=description)
        return self

    def delete(self):
        # remove all the posts from this album
        for post_id in self.post_manager.dynamo.generate_post_ids_in_album(self.id):
            post = self.post_manager.get_post(post_id)
            post.set_album(None)

        # delete the album art
        if (art_hash := self.item.get('artHash')):
            self.delete_art_images(art_hash)

        # order matters to moto (in test suite), but not on dynamo
        transacts = [
            self.user_manager.dynamo.transact_decrement_album_count(self.user_id),
            self.dynamo.transact_delete_album(self.id),
        ]
        transact_exceptions = [
            exceptions.AlbumException(f'Unable to decrement album count for user `{self.user_id}`'),
            exceptions.AlbumException(f'Album `{self.id}` does not exist'),
        ]
        self.dynamo.client.transact_write_items(transacts, transact_exceptions)
        return self

    def get_next_first_rank(self):
        "Return the next rank to be used for a post to appear as first in the album"
        rank_spaces = self.item.get('rankCount', 0) + 2
        return 2 / rank_spaces - 1

    def get_next_last_rank(self):
        "Return the next rank to be used for a post to appear as last in the album"
        rank_spaces = self.item.get('rankCount', 0) + 2
        return 1 - 2 / rank_spaces

    def get_art_image_url(self, size):
        art_image_path = self.get_art_image_path(size)
        if art_image_path:
            return self.cloudfront_client.generate_presigned_url(art_image_path, ['GET', 'HEAD'])
        return f'https://{self.frontend_resources_domain}/default-album-art/{size.filename}'

    def get_art_image_path(self, size, art_hash=None):
        art_hash = art_hash or self.item.get('artHash')
        if not art_hash:
            return None
        return '/'.join([self.user_id, 'album', self.id, art_hash, size.filename])

    def get_post_ids_for_art(self):
        # we only want a square number of post ids, max of 4x4
        post_ids_gen = self.post_manager.dynamo.generate_post_ids_in_album(self.id, completed=True)
        post_ids = list(itertools.islice(post_ids_gen, 16))
        if len(post_ids) < 16:
            post_ids = post_ids[:9]
        if len(post_ids) < 9:
            post_ids = post_ids[:4]
        if len(post_ids) < 4:
            post_ids = post_ids[:1]
        return post_ids

    def update_art_if_needed(self):
        post_ids = self.get_post_ids_for_art()
        if post_ids:
            new_art_hash = hashlib.md5(''.join(post_ids).encode('utf-8')).hexdigest()
        else:
            new_art_hash = None

        old_art_hash = self.item.get('artHash')
        if new_art_hash == old_art_hash:
            return self  # no changes

        posts = [self.post_manager.get_post(post_id) for post_id in post_ids]
        if len(posts) == 0:
            new_native_buf = None
        elif len(posts) == 1:
            new_native_buf = posts[0].get_native_image_buffer()
        else:
            image_data_buffers = [post.get_1080p_image_buffer() for post in posts]
            new_native_buf = art.generate_zoomed_grid(image_data_buffers)

        if new_native_buf:
            self.save_art_images(new_art_hash, new_native_buf)

        self.item = self.dynamo.set_album_art_hash(self.id, new_art_hash)

        if old_art_hash:
            self.delete_art_images(old_art_hash)

        return self

    def delete_art_images(self, art_hash):
        # remove the images from s3
        for size in image_size.JPEGS:
            path = self.get_art_image_path(size, art_hash=art_hash)
            self.s3_uploads_client.delete_object(path)

    def save_art_images(self, art_hash, native_image_buf):
        # save the native size to S3
        path = self.get_art_image_path(image_size.NATIVE, art_hash=art_hash)
        self.s3_uploads_client.put_object(path, native_image_buf.read(), self.jpeg_content_type)

        # generate and save thumbnails
        native_image_buf.seek(0)
        image = Image.open(native_image_buf)
        for size in image_size.THUMBNAILS:  # ordered by decreasing size
            image.thumbnail(size.max_dimensions, resample=Image.LANCZOS)
            in_mem_file = BytesIO()
            image.save(in_mem_file, format='JPEG', quality=100, icc_profile=image.info.get('icc_profile'))
            in_mem_file.seek(0)
            path = self.get_art_image_path(size, art_hash=art_hash)
            self.s3_uploads_client.put_object(path, in_mem_file.read(), self.jpeg_content_type)
