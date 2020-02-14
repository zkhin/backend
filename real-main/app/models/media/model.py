import logging
from io import BytesIO

from colorthief import ColorThief
from PIL import Image, ImageOps
import requests

from . import enums, exceptions

logger = logging.getLogger()


class Media:

    enums = enums
    exceptions = exceptions

    jpeg_content_type = 'image/jpeg'
    file_ext = 'jpg'
    sizes = {
        enums.MediaSize.K4: [3840, 2160],
        enums.MediaSize.P1080: [1920, 1080],
        enums.MediaSize.P480: [854, 480],
        enums.MediaSize.P64: [114, 64],
    }

    def __init__(self, item, media_dynamo, cloudfront_client=None, secrets_manager_client=None,
                 s3_uploads_client=None):
        self.dynamo = media_dynamo

        if cloudfront_client:
            self.cloudfront_client = cloudfront_client
        if s3_uploads_client:
            self.s3_uploads_client = s3_uploads_client
        if secrets_manager_client:
            self.post_verification_api_creds_getter = secrets_manager_client.get_post_verification_api_creds

        self.item = item
        self.id = item['mediaId']

        if self.item and 'mediaStatus' not in self.item:
            # When media objects are stored in feed objects, they are assumed to be
            # in UPLOADED state and it is not explicity saved in dynamo
            self.item['mediaStatus'] = enums.MediaStatus.UPLOADED

    @property
    def native_image_data_stream(self):
        if not hasattr(self, '_native_image_data'):
            path = self.get_s3_path(enums.MediaSize.NATIVE)
            self._native_image_data = self.s3_uploads_client.get_object_data_stream(path).read()
        return BytesIO(self._native_image_data)

    @property
    def p1080_image_data_stream(self):
        if not hasattr(self, '_p1080_image_data'):
            path = self.get_s3_path(enums.MediaSize.P1080)
            self._p1080_image_data = self.s3_uploads_client.get_object_data_stream(path).read()
        return BytesIO(self._p1080_image_data)

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
        have_writeonly_url = (enums.MediaStatus.AWAITING_UPLOAD, enums.MediaStatus.ERROR)
        if self.item['mediaStatus'] not in have_writeonly_url:
            return None

        path = self.get_s3_path(enums.MediaSize.NATIVE)
        return self.cloudfront_client.generate_presigned_url(path, ['PUT'])

    def get_s3_path(self, size):
        "From within the user's directory, return the path to the s3 object of the requested size"
        filename = f'{size}.{self.file_ext}'
        return '/'.join([self.item['userId'], 'post', self.item['postId'], 'media', self.item['mediaId'], filename])

    def has_all_s3_objects(self):
        for media_size in enums.MediaSize._ALL:
            path = self.get_s3_path(media_size)
            if not self.s3_uploads_client.exists(path):
                return False
        return True

    def delete_all_s3_objects(self):
        for media_size in enums.MediaSize._ALL:
            path = self.get_s3_path(media_size)
            self.s3_uploads_client.delete_object(path)

    def process_upload(self):
        assert self.item['mediaStatus'] in (enums.MediaStatus.AWAITING_UPLOAD, enums.MediaStatus.ERROR), 'Bad status'

        # mark as processing before we start downloading the file from S3
        self.set_status(enums.MediaStatus.PROCESSING_UPLOAD)

        # only accept jpeg uploads
        if not self.is_original_jpeg():
            self.set_status(enums.MediaStatus.ERROR)
            raise exceptions.MediaException(f'Non-jpeg image uploaded for media `{self.id}`')

        self.set_is_verified()
        self.set_height_and_width()
        self.set_colors()
        self.set_thumbnails()
        self.set_checksum()
        self.set_status(enums.MediaStatus.UPLOADED)
        return self

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
            raise exceptions.MediaException(msg)
        try:
            is_verified = resp.json()['data']['isVerified']
        except Exception:
            msg = f'Unable to parse reponse from post verification service with body: `{resp.text}`'
            raise exceptions.MediaException(msg)

        self.item = self.dynamo.set_is_verified(self.id, is_verified)
        return self

    def set_height_and_width(self):
        image = Image.open(self.native_image_data_stream)
        width, height = image.size
        self.item = self.dynamo.set_height_and_width(self.id, height, width)
        return self

    def set_colors(self):
        try:
            colors = ColorThief(self.native_image_data_stream).get_palette(color_count=5)
        except Exception as err:
            logger.warning(f'ColorTheif failed to calculate color palette with error `{err}` for media `{self.id}`')
        else:
            self.item = self.dynamo.set_colors(self.id, colors)
        return self

    def set_thumbnails(self):
        for size, dims in self.sizes.items():
            image = Image.open(self.native_image_data_stream)
            image = ImageOps.exif_transpose(image)
            image.thumbnail(dims)
            in_mem_file = BytesIO()
            image.save(in_mem_file, format='JPEG')
            in_mem_file.seek(0)
            path = self.get_s3_path(size)
            self.s3_uploads_client.put_object(path, in_mem_file.read(), self.jpeg_content_type)

    def set_checksum(self):
        path = self.get_s3_path(enums.MediaSize.NATIVE)
        checksum = self.s3_uploads_client.get_object_checksum(path)
        self.item = self.dynamo.set_checksum(self.item, checksum)
        return self

    def is_original_jpeg(self):
        try:
            image = Image.open(self.native_image_data_stream)
        except Exception:
            return False
        return image.format == 'JPEG'

    def set_status(self, status):
        transact = self.dynamo.transact_set_status(self.item, status)
        self.dynamo.client.transact_write_items([transact])
        self.item['mediaStatus'] = status  # not worry about stale in-memory copies of indexes
        return self
