# keep in sync with object created handlers defined serverless.yml
VIDEO_ORIGINAL_FILENAME = 'video-original.mov'
VIDEO_HLS_PREFIX = 'video-hls/video'
VIDEO_POSTER_PREFIX = 'video-poster/poster'
IMAGE_DIR = 'image'


class PostStatus:
    PENDING = 'PENDING'
    PROCESSING = 'PROCESSING'
    COMPLETED = 'COMPLETED'
    ERROR = 'ERROR'
    ARCHIVED = 'ARCHIVED'
    DELETING = 'DELETING'

    _ALL = (PENDING, COMPLETED, ERROR, ARCHIVED, DELETING)


class PostType:
    TEXT_ONLY = 'TEXT_ONLY'
    IMAGE = 'IMAGE'
    VIDEO = 'VIDEO'

    _ALL = (TEXT_ONLY, IMAGE, VIDEO)


class PostNotificationType:
    COMPLETED = 'COMPLETED'

    _ALL = COMPLETED
