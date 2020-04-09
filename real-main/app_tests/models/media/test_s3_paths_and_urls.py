from app.models.media.model import Media
from app.utils import image_size


def test_get_s3_path_schema_version():
    item = {
        'userId': 'us-east-1:user-id',
        'postId': 'post-id',
        'mediaId': 'media-id',
    }

    media = Media(item, None)
    path = media.get_s3_path(image_size.NATIVE)
    assert path == 'us-east-1:user-id/post/post-id/image/native.jpg'
