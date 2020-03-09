# keep in sync with object created handlers defined serverless.yml


class _ImageSize:

    file_ext = 'jpg'

    def __init__(self, name, max_dimensions):
        self.name = name
        self.max_dimensions = max_dimensions
        self.filename = f'{self.name}.{self.file_ext}'


NATIVE = _ImageSize('native', None)
K4 = _ImageSize('4K', (3840, 2160))  # TODO: change name to '4k' with lowercase k
P1080 = _ImageSize('1080p', (1920, 1080))
P480 = _ImageSize('480p', (854, 480))
P64 = _ImageSize('64p', (114, 64))

ALL = (NATIVE, K4, P1080, P480, P64)
THUMBNAILS = (K4, P1080, P480, P64)  # ordered by decreasing size
