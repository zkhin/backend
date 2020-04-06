import base64
import logging
from io import BytesIO

from colorthief import ColorThief
from PIL import Image, ImageOps

from app.utils import image_size

from . import enums, exceptions

logger = logging.getLogger()


class Media:

    enums = enums
    exceptions = exceptions

    jpeg_content_type = 'image/jpeg'

    def __init__(self, item, media_dynamo, cloudfront_client=None, post_verification_client=None,
                 s3_uploads_client=None):
        self.dynamo = media_dynamo

        if cloudfront_client:
            self.cloudfront_client = cloudfront_client
        if post_verification_client:
            self.post_verification_client = post_verification_client
        if s3_uploads_client:
            self.s3_uploads_client = s3_uploads_client

        self.item = item
        self.id = item['mediaId']

        if self.item and 'mediaStatus' not in self.item:
            # When media objects are stored in feed objects, they are assumed to be
            # in UPLOADED state and it is not explicity saved in dynamo
            self.item['mediaStatus'] = enums.MediaStatus.UPLOADED

    def get_native_image_buffer(self):
        if not hasattr(self, '_native_image_data'):
            path = self.get_s3_path(image_size.NATIVE)
            self._native_image_data = self.s3_uploads_client.get_object_data_stream(path).read()
        return BytesIO(self._native_image_data)

    def get_1080p_image_buffer(self):
        if not hasattr(self, '_1080p_image_data'):
            path = self.get_s3_path(image_size.P1080)
            self._1080p_image_data = self.s3_uploads_client.get_object_data_stream(path).read()
        return BytesIO(self._1080p_image_data)

    def refresh_item(self, strongly_consistent=False):
        self.item = self.dynamo.get_media(self.id, strongly_consistent=strongly_consistent)
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

        path = self.get_s3_path(image_size.NATIVE)
        return self.cloudfront_client.generate_presigned_url(path, ['PUT'])

    def get_s3_path(self, size):
        "From within the user's directory, return the path to the s3 object of the requested size"
        if self.item.get('schemaVersion', 0) > 0:
            return '/'.join([self.item['userId'], 'post', self.item['postId'], 'image', size.filename])
        return '/'.join([
            self.item['userId'], 'post', self.item['postId'], 'media', self.item['mediaId'], size.filename,
        ])

    def has_all_s3_objects(self):
        for size in image_size.ALL:
            path = self.get_s3_path(size)
            if not self.s3_uploads_client.exists(path):
                return False
        return True

    def delete_all_s3_objects(self):
        for size in image_size.ALL:
            path = self.get_s3_path(size)
            self.s3_uploads_client.delete_object(path)

    def upload_native_image_data_base64(self, image_data):
        "Given a base64-encoded string of image data, set the native image in S3 and our cached copy of the data"
        self._native_image_data = base64.b64decode(image_data)
        path = self.get_s3_path(image_size.NATIVE)
        self.s3_uploads_client.put_object(path, self.get_native_image_buffer(), self.jpeg_content_type)

    def process_upload(self):
        allowed = (enums.MediaStatus.AWAITING_UPLOAD, enums.MediaStatus.ERROR)
        media_status = self.item['mediaStatus']
        assert media_status in allowed, f'Media is in non-processable status: `{media_status}`'

        # mark as processing before we start downloading the file from S3
        if media_status != enums.MediaStatus.PROCESSING_UPLOAD:
            self.set_status(enums.MediaStatus.PROCESSING_UPLOAD)

        # only accept jpeg uploads
        if not self.is_original_jpeg():
            raise exceptions.MediaException(f'Non-jpeg image uploaded for media `{self.id}`')

        try:
            self.set_thumbnails()
        except Exception as err:
            raise exceptions.MediaException(f'Unable to generate thumbnails for media `{self.id}`: {err}')

        self.set_is_verified()
        self.set_height_and_width()
        self.set_colors()
        self.set_checksum()
        self.set_status(enums.MediaStatus.UPLOADED)
        return self

    def set_is_verified(self):
        image_url = self.get_readonly_url(image_size.NATIVE)
        is_verified = self.post_verification_client.verify_image(
            image_url, taken_in_real=self.item.get('takenInReal'), original_format=self.item.get('originalFormat'),
        )
        self.item = self.dynamo.set_is_verified(self.id, is_verified)
        return self

    def set_height_and_width(self):
        image = Image.open(self.get_native_image_buffer())
        width, height = image.size
        self.item = self.dynamo.set_height_and_width(self.id, height, width)
        return self

    def set_colors(self):
        try:
            colors = ColorThief(self.get_native_image_buffer()).get_palette(color_count=5)
        except Exception as err:
            logger.warning(f'ColorTheif failed to calculate color palette with error `{err}` for media `{self.id}`')
        else:
            self.item = self.dynamo.set_colors(self.id, colors)
        return self

    def set_thumbnails(self):
        image = Image.open(self.get_native_image_buffer())
        image = ImageOps.exif_transpose(image)
        for size in image_size.THUMBNAILS:  # ordered by decreasing size
            image.thumbnail(size.max_dimensions, resample=Image.LANCZOS)
            in_mem_file = BytesIO()
            image.save(in_mem_file, format='JPEG', quality=95, icc_profile=image.info.get('icc_profile'))
            in_mem_file.seek(0)
            path = self.get_s3_path(size)
            self.s3_uploads_client.put_object(path, in_mem_file.read(), self.jpeg_content_type)

    def set_checksum(self):
        path = self.get_s3_path(image_size.NATIVE)
        checksum = self.s3_uploads_client.get_object_checksum(path)
        self.item = self.dynamo.set_checksum(self.item, checksum)
        return self

    def is_original_jpeg(self):
        try:
            image = Image.open(self.get_native_image_buffer())
        except Exception:
            return False
        return image.format == 'JPEG'

    def set_status(self, status):
        transact = self.dynamo.transact_set_status(self.item, status)
        self.dynamo.client.transact_write_items([transact])
        self.item['mediaStatus'] = status  # not worry about stale in-memory copies of indexes
        return self
