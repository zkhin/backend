import hashlib
from io import BytesIO
import itertools
import logging
import math
import os

from PIL import Image

from app.models.media.enums import MediaExt, MediaSize

from . import exceptions

logger = logging.getLogger()

FRONTEND_RESOURCES_DOMAIN = os.environ.get('FRONTEND_RESOURCES_DOMAIN')


class Album:

    exceptions = exceptions
    art_image_file_ext = MediaExt.JPG
    jpeg_content_type = 'image/jpeg'
    sizes = {
        MediaSize.K4: [3840, 2160],
        MediaSize.P1080: [1920, 1080],
        MediaSize.P480: [854, 480],
        MediaSize.P64: [114, 64],
    }

    def __init__(self, album_item, album_dynamo, cloudfront_client=None, s3_uploads_client=None,
                 user_manager=None, post_manager=None, media_manager=None,
                 frontend_resources_domain=FRONTEND_RESOURCES_DOMAIN):
        self.dynamo = album_dynamo
        if cloudfront_client:
            self.cloudfront_client = cloudfront_client
        if s3_uploads_client:
            self.s3_uploads_client = s3_uploads_client
        if media_manager:
            self.media_manager = media_manager
        if post_manager:
            self.post_manager = post_manager
        if user_manager:
            self.user_manager = user_manager
        self.id = album_item['albumId']
        self.item = album_item
        self.frontend_resources_domain = frontend_resources_domain

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

        # delete the album art
        if (art_hash := self.item.get('artHash')):
            self.delete_art_images(art_hash)

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

    def get_art_image_url(self, size):
        art_image_path = self.get_art_image_path(size)
        if art_image_path:
            return self.cloudfront_client.generate_presigned_url(art_image_path, ['GET', 'HEAD'])
        return f'https://{self.frontend_resources_domain}/default-album-art/{size}.{self.art_image_file_ext}'

    def get_art_image_path(self, size, art_hash=None):
        art_hash = art_hash or self.item.get('artHash')
        if not art_hash:
            return None
        filename = f'{size}.{self.art_image_file_ext}'
        return '/'.join([self.item['ownedByUserId'], 'album', self.id, art_hash, filename])

    def update_art_if_needed(self):
        # we only want a square number of post ids, max of 4x4
        post_ids_gen = self.post_manager.dynamo.generate_post_ids_in_album(self.id, completed=True)
        post_ids = list(itertools.islice(post_ids_gen, 16))
        if len(post_ids) < 16:
            post_ids = post_ids[:9]
        if len(post_ids) < 9:
            post_ids = post_ids[:4]
        if len(post_ids) < 4:
            post_ids = post_ids[:1]

        if post_ids:
            new_art_hash = hashlib.md5(''.join(post_ids).encode('utf-8')).hexdigest()
        else:
            new_art_hash = None

        old_art_hash = self.item.get('artHash')
        if new_art_hash == old_art_hash:
            return self  # no changes

        if len(post_ids) == 1:
            self.update_art_images_one_post(new_art_hash, post_ids[0])
        elif len(post_ids) > 1:
            self.update_art_images_grid(new_art_hash, post_ids)

        self.item = self.dynamo.set_album_art_hash(self.id, new_art_hash)

        if old_art_hash:
            self.delete_art_images(old_art_hash)

        return self

    def delete_art_images(self, art_hash):
        # remove the images from s3
        for size in MediaSize._ALL:
            path = self.get_art_image_path(size, art_hash=art_hash)
            self.s3_uploads_client.delete_object(path)

    def update_art_images_one_post(self, art_hash, post_id):
        # copy the images from the post to the album
        media_item = next(self.media_manager.dynamo.generate_by_post(post_id, uploaded=True), None)
        if not media_item:
            # shouldn't get here, as the post should be in completed state and have media
            raise Exception(f'Did not find uploaded media for post `{post_id}`')
        media = self.media_manager.init_media(media_item)
        for size in MediaSize._ALL:
            source_path = media.get_s3_path(size)
            dest_path = self.get_art_image_path(size, art_hash=art_hash)
            self.s3_uploads_client.copy_object(source_path, dest_path)

    def update_art_images_grid(self, art_hash, post_ids):
        assert len(post_ids) in (4, 9, 16), f'Unexpected number of post_ids: `{len(post_ids)}`'

        # collect all the 1080p thumbs from all the post images
        images = []
        max_width, max_height = 0, 0
        for post_id in post_ids:
            media_item = next(self.media_manager.dynamo.generate_by_post(post_id, uploaded=True), None)
            if not media_item:
                # shouldn't get here, as the post should be in completed state and have media
                raise Exception(f'Did not find uploaded media for post `{post_id}`')
            media = self.media_manager.init_media(media_item)
            image = Image.open(media.p1080_image_data_stream)
            max_width = max(max_width, image.size[0])
            max_height = max(max_height, image.size[1])
            images.append(image)

        # paste those thumbs together as a grid
        # Min size will be 4k since max_width and max_height come from 1080p thumbs
        stride = int(math.sqrt(len(post_ids)))
        target_image = Image.new('RGB', (max_width * stride, max_height * stride))
        for row in range(0, stride):
            for column in range(0, stride):
                image = images[row * stride + column]
                width, height = image.size
                loc = (column * max_width + (max_width - width) // 2, row * max_height + (max_height - height) // 2)
                target_image.paste(image, loc)

        # convert to jpeg
        in_mem_file = BytesIO()
        target_image.save(in_mem_file, format='JPEG')
        in_mem_file.seek(0)

        # save the native size to S3
        path = self.get_art_image_path(MediaSize.NATIVE, art_hash=art_hash)
        self.s3_uploads_client.put_object(path, in_mem_file.read(), self.jpeg_content_type)

        # generate and save thumbnails
        for size, dims in self.sizes.items():
            target_image.thumbnail(dims)
            in_mem_file = BytesIO()
            target_image.save(in_mem_file, format='JPEG')
            in_mem_file.seek(0)
            path = self.get_art_image_path(size, art_hash=art_hash)
            self.s3_uploads_client.put_object(path, in_mem_file.read(), self.jpeg_content_type)
