import io

import PIL.Image
import PIL.ImageOps
import pyheif

from app.utils import image_size

from .exceptions import PostException


class CachedImage:

    jpeg_content_type = 'image/jpeg'
    heic_content_type = 'image/heic'

    def __init__(self, post_id, img_size, s3_client=None, s3_path=None, source=None):
        assert (s3_client and s3_path) or source, 'Either s3 kwargs or source required'

        self.post_id = post_id
        self.image_size = img_size
        self.s3_client = s3_client
        self.s3_path = s3_path
        self.source = source

        self.is_synced = None
        self._data = None

    @property
    def content_type(self):
        return self.heic_content_type if self.image_size == image_size.NATIVE_HEIC else self.jpeg_content_type

    @property
    def is_empty(self):
        return not bool(self._data)

    def get_fh(self):
        if self.is_synced is None:
            self.refresh()
        return io.BytesIO(self._data)

    def get_image(self):
        fh = self.get_fh()

        if self.image_size == image_size.NATIVE_HEIC:
            try:
                heif_file = pyheif.read(fh)
            except (ValueError, pyheif.error.HeifError) as err:
                raise PostException(f'Unable to read HEIC file for post `{self.post_id}`: {err}')
            return PIL.Image.frombytes(
                heif_file.mode, heif_file.size, heif_file.data, 'raw', heif_file.mode, heif_file.stride
            )

        else:
            try:
                return PIL.ImageOps.exif_transpose(PIL.Image.open(fh))
            except PostException:
                raise
            except Exception as err:
                raise PostException(f'Unable to decode native jpeg data for post `{self.post_id}`: {err}')

    def refresh(self):
        if self.source:
            fh = self.source(self.image_size.max_dimensions)
        else:
            try:
                fh = self.s3_client.get_object_data_stream(self.s3_path)
            except self.s3_client.exceptions.NoSuchKey:
                raise PostException(f'{self.image_size.filename} image data not found for post `{self.post_id}`')

        self._data = fh.read()
        self.is_synced = True
        return self

    def set(self, fh=None, image=None):
        assert (fh is not None) != (image is not None)  # python has no logical xor infix operator :(

        if image:
            fh = io.BytesIO()
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
                raise PostException(f'Unable to save pil image for post `{self.post_id}`: {err}')

        fh.seek(0)
        self.is_synced = False
        self._data = fh.read()
        return self

    def flush(self, include_deletes=False):
        if not self.is_synced:
            if self._data:
                self.s3_client.put_object(self.s3_path, self.get_fh(), self.content_type)
            else:
                if not include_deletes:
                    raise Exception('Refusing to flush back empty cache without `include_deletes` kwarg')
                self.s3_client.delete_object(self.s3_path)
            self.is_synced = True
        return self

    def clear(self):
        if self._data is not None:
            self._data = None
            self.is_synced = False
        return self
