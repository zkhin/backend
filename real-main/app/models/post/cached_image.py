from io import BytesIO

from PIL import Image, ImageOps
import pyheif

from app.utils import image_size

from .enums import PostType
from .exceptions import PostException
from .text_image import generate_text_image


class CachedImage:

    jpeg_content_type = 'image/jpeg'
    heic_content_type = 'image/heic'

    def __init__(self, post, image_size):
        self.post = post
        if hasattr(post, 's3_uploads_client'):
            self.s3_client = post.s3_uploads_client
        self.s3_path = post.get_image_path(image_size)
        self.image_size = image_size
        self._is_dirty = False
        self._data = None

    @property
    def content_type(self):
        return self.heic_content_type if self.image_size == image_size.NATIVE_HEIC else self.jpeg_content_type

    @property
    def is_empty(self):
        return not bool(self._data)

    @property
    def is_dirty(self):
        return self._is_dirty

    def get_fh(self):
        if not self._data:
            self.fill()
        return BytesIO(self._data)

    def get_image(self):
        fh = self.get_fh()

        if self.image_size == image_size.NATIVE_HEIC:
            try:
                heif_file = pyheif.read_heif(fh)
            except pyheif.error.HeifError as err:
                raise PostException(f'Unable to read HEIC file for post `{self.post.id}`: {err}')
            return Image.frombytes(mode=heif_file.mode, size=heif_file.size, data=heif_file.data)

        else:
            try:
                return ImageOps.exif_transpose(Image.open(fh))
            except PostException:
                raise
            except Exception as err:
                raise PostException(f'Unable to decode native jpeg data for post `{self.post.id}`: {err}')

    def fill(self):
        if self.post.type == PostType.TEXT_ONLY:
            size = image_size.K4 if self.image_size == image_size.NATIVE else self.image_size
            fh = generate_text_image(self.post.item['text'], size.max_dimensions)

        elif self.post.type in (PostType.IMAGE, PostType.VIDEO):
            try:
                fh = self.s3_client.get_object_data_stream(self.s3_path)
            except self.s3_client.exceptions.NoSuchKey:
                raise PostException(f'{self.image_size.filename} image data not found for post `{self.post.id}`')

        else:
            raise Exception(f'Unexpected post type `{self.post.type}` for post `{self.post.id}`')

        self._data = fh.read()
        return self

    def set(self, fh=None, image=None):
        assert (fh is not None) != (image is not None)  # python has no logical xor infix operator :(

        if image:
            fh = BytesIO()
            # Note that PIL/Pillow's save method treats None differently than not present for some kwargs
            kwargs = {
                'format': 'JPEG',
                'quality': 100,
            }
            if 'icc_profile' in image.info:
                kwargs['icc_profile'] = image.info['icc_profile']
            if 'exif' in image.info:
                kwargs['exif'] = image.info['exif']
            try:
                image.save(fh, **kwargs)
            except Exception as err:
                raise PostException(f'Unable to save pil image for post `{self.post.id}`: {err}')

        fh.seek(0)
        self._is_dirty = True
        self._data = fh.read()
        return self

    def flush(self):
        if not self._is_dirty:
            return
        self.s3_client.put_object(self.s3_path, self.get_fh(), self.content_type)
        self._is_dirty = False
        return self
