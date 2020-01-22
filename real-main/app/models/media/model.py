import logging
from io import BytesIO

from PIL import Image, ImageOps
import requests

from . import enums, exceptions
from .dynamo import MediaDynamo

logger = logging.getLogger()


class Media:

    enums = enums
    exceptions = exceptions

    client_names = ['cloudfront', 'dynamo', 's3_uploads']
    jpeg_content_type = 'image/jpeg'
    sizes = {
        enums.MediaSize.K4: [3840, 2160],
        enums.MediaSize.P1080: [1920, 1080],
        enums.MediaSize.P480: [854, 480],
        enums.MediaSize.P64: [114, 64],
    }

    def __init__(self, item, clients):
        self.clients = clients
        for client_name in self.client_names:
            if client_name in clients:
                setattr(self, f'{client_name}_client', clients[client_name])

        if 'dynamo' in clients:
            self.dynamo = MediaDynamo(clients['dynamo'])
        if 'secrets_manager' in clients:
            self.post_verification_api_creds_getter = clients['secrets_manager'].get_post_verification_api_creds

        self.item = item
        self.id = item['mediaId']

        if self.item and 'mediaStatus' not in self.item:
            # When media objects are stored in feed objects, they are assumed to be
            # in UPLOADED state and it is not explicity saved in dynamo
            self.item['mediaStatus'] = enums.MediaStatus.UPLOADED

    @property
    def file_ext(self):
        mediaType = self.item['mediaType']
        if mediaType == enums.MediaType.IMAGE:
            return enums.MediaExt.JPG
        if mediaType == enums.MediaType.VIDEO:
            return enums.MediaExt.MP4
        raise Exception(f'No file extension yet defined for media type `{mediaType}`')

    @property
    def original_image_data_stream(self):
        if not hasattr(self, '_original_image_data'):
            path = self.get_s3_path(enums.MediaSize.NATIVE)
            self._original_image_data = self.s3_uploads_client.get_object_data_stream(path).read()
        return BytesIO(self._original_image_data)

    def refresh_item(self):
        self.item = self.dynamo.get_media(self.id)
        return self

    def get_readonly_url(self, size):
        have_ro_url = (enums.MediaStatus.PROCESSING_UPLOAD, enums.MediaStatus.UPLOADED, enums.MediaStatus.ARCHIVED)
        if self.item['mediaStatus'] not in have_ro_url:
            return None

        path = self.get_s3_path(size)
        return self.cloudfront_client.generate_presigned_url(path, ['GET', 'HEAD'])

    def get_writeonly_url(self):
        have_writeonly_url = (enums.MediaStatus.AWAITING_UPLOAD, enums.MediaStatus.UPLOADING, enums.MediaStatus.ERROR)
        if self.item['mediaStatus'] not in have_writeonly_url:
            return None

        path = self.get_s3_path(enums.MediaSize.NATIVE)
        return self.cloudfront_client.generate_presigned_url(path, ['PUT'])

    def get_s3_path(self, size):
        "From within the user's directory, return the path to the s3 object of the requested size"
        filename = f'{size}.{self.file_ext}'
        return '/'.join([self.item['userId'], 'post', self.item['postId'], 'media', self.item['mediaId'], filename])

    def has_all_s3_objects(self):
        mediaType = self.item['mediaType']

        if mediaType == enums.MediaType.IMAGE:
            for media_size in enums.MediaSize._ALL:
                path = self.get_s3_path(media_size)
                if not self.s3_uploads_client.exists(path):
                    return False
            return True

        if mediaType == enums.MediaType.VIDEO:
            path = self.get_s3_path(enums.MediaSize.NATIVE)
            return self.s3_uploads_client.exists(path)

        raise Exception(f'Unknown media tyep `{mediaType}`')

    def delete_all_s3_objects(self):
        for media_size in enums.MediaSize._ALL:
            path = self.get_s3_path(media_size)
            self.s3_uploads_client.delete_object(path)

    def set_is_verified(self):
        api_creds = self.post_verification_api_creds_getter()
        headers = {'x-api-key': api_creds['key']}
        url = api_creds['root'] + 'verify/image'

        data = {
            'url': self.get_readonly_url(enums.MediaSize.NATIVE),
            'metadata': {},
        }
        if 'takenInReal' in self.item:
            data['metadata']['takenInReal'] = self.item['takenInReal']
        if 'originalFormat' in self.item:
            data['metadata']['originalFormat'] = self.item['originalFormat']

        # synchronous for now. Note this generally runs in an async env already: an s3-object-created handler
        resp = requests.post(url, headers=headers, json=data)
        if resp.status_code != 200:
            msg = f'Received error from post verification service: `{resp.status_code}` with body: `{resp.text}`'
            raise Exception(msg)
        try:
            is_verified = resp.json()['data']['isVerified']
        except Exception:
            msg = f'Unable to parse reponse from post verification service with body: `{resp.text}`'
            raise Exception(msg)

        self.item = self.dynamo.set_is_verified(self.id, is_verified)
        return self

    def set_height_and_width(self):
        image = Image.open(self.original_image_data_stream)
        width, height = image.size
        self.item = self.dynamo.set_height_and_width(self.id, height, width)
        return self

    def set_thumbnails(self):
        for size, dims in self.sizes.items():
            image = Image.open(self.original_image_data_stream)
            image = ImageOps.exif_transpose(image)
            image.thumbnail(dims)
            in_mem_file = BytesIO()
            image.save(in_mem_file, format='JPEG')
            in_mem_file.seek(0)
            path = self.get_s3_path(size)
            self.s3_uploads_client.put_object(path, in_mem_file.read(), self.jpeg_content_type)

    def is_original_jpeg(self):
        try:
            image = Image.open(self.original_image_data_stream)
        except Exception:
            return False
        return image.format == 'JPEG'

    def set_status(self, status):
        transact = self.dynamo.transact_set_status(self.item, status)
        self.dynamo.client.transact_write_items([transact])
        self.item['mediaStatus'] = status  # not worry about stale in-memory copies of indexes
        return self
