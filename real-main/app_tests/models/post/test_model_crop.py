from os import path
import uuid

from PIL import Image
import pytest

from app.models.post.enums import PostType
from app.models.post.exceptions import PostException
from app.utils import image_size


grant_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'grant.jpg')
grant_height = 320
grant_width = 240

heic_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'IMG_0265.HEIC')
heic_height = 3024
heic_width = 4032


@pytest.fixture
def user(user_manager, cognito_client):
    user_id = str(uuid.uuid4())
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username=user_id)
    yield user_manager.create_cognito_only_user(user_id, str(uuid.uuid4())[:8])


@pytest.fixture
def jpeg_image_post(post_manager, user, s3_uploads_client):
    post = post_manager.add_post(user.id, str(uuid.uuid4()), PostType.IMAGE, image_input={'imageFormat': 'JPEG'})
    s3_path = post.get_image_path(image_size.NATIVE)
    s3_uploads_client.put_object(s3_path, open(grant_path, 'rb'), 'image/jpeg')
    yield post


def heic_image_post(post_manager, user, s3_uploads_client):
    image_input = {
        'imageFormat': 'HEIC',
        'crop': {'upperLeft': {'x': 42, 'y': 24}, 'lowerRight': {'x': 200, 'y': 150}},
    }
    post = post_manager.add_post(user.id, str(uuid.uuid4()), PostType.IMAGE, image_input=image_input)
    s3_path = post.get_image_path(image_size.NATIVE_HEIC)
    s3_uploads_client.put_object(s3_path, open(heic_path, 'rb'), 'image/jpeg')
    yield post


def test_cannot_crop_wrong_post_type(post_manager, user):
    text_only_post = post_manager.add_post(user.id, str(uuid.uuid4()), PostType.TEXT_ONLY, text='t')
    with pytest.raises(AssertionError, match='post type'):
        text_only_post.crop_native_jpeg_cache()

    video_post = post_manager.add_post(user.id, str(uuid.uuid4()), PostType.VIDEO, text='t')
    with pytest.raises(AssertionError, match='post type'):
        video_post.crop_native_jpeg_cache()


def test_cannot_crop_no_crop(post_manager, user):
    post = post_manager.add_post(user.id, str(uuid.uuid4()), PostType.IMAGE)
    with pytest.raises(AssertionError, match='no crop specified'):
        post.crop_native_jpeg_cache()


@pytest.mark.parametrize('crop', [
    {'upperLeft': {'x': 0, 'y': 0}, 'lowerRight': {'x': grant_width, 'y': grant_height + 1}},
])
def test_cannot_overcrop_jpeg_post_height(user, jpeg_image_post, crop):
    jpeg_image_post.image_item['crop'] = crop
    with pytest.raises(PostException, match='not tall enough'):
        jpeg_image_post.crop_native_jpeg_cache()


@pytest.mark.parametrize('crop', [
    {'upperLeft': {'x': 0, 'y': 0}, 'lowerRight': {'x': grant_width + 1, 'y': grant_height}},
])
def test_cannot_overcrop_jpeg_post_width(user, jpeg_image_post, crop):
    jpeg_image_post.image_item['crop'] = crop
    with pytest.raises(PostException, match='not wide enough'):
        jpeg_image_post.crop_native_jpeg_cache()


@pytest.mark.parametrize('crop', [
    {'upperLeft': {'x': 0, 'y': grant_height - 1}, 'lowerRight': {'x': 1, 'y': grant_height}},
    {'upperLeft': {'x': grant_width - 1, 'y': 0}, 'lowerRight': {'x': grant_width, 'y': 1}},
    {'upperLeft': {'x': 0, 'y': 0}, 'lowerRight': {'x': 1, 'y': 1}},
])
def test_successful_jpeg_crop_to_minimal_image(user, jpeg_image_post, crop, s3_uploads_client):
    # crop the image
    jpeg_image_post.image_item['crop'] = crop
    jpeg_image_post.crop_native_jpeg_cache()

    # check the new image dimensions
    image = jpeg_image_post.native_jpeg_cache.get_image()
    width, height = image.size
    assert width == 1
    assert height == 1


@pytest.mark.parametrize('crop', [
    {'upperLeft': {'x': 0, 'y': 0}, 'lowerRight': {'x': grant_width, 'y': grant_height}},
])
def test_successful_jpeg_crop_off_nothing(user, jpeg_image_post, crop, s3_uploads_client):
    # crop the image
    jpeg_image_post.image_item['crop'] = crop
    jpeg_image_post.crop_native_jpeg_cache()

    # check the new image dimensions
    image = jpeg_image_post.native_jpeg_cache.get_image()
    width, height = image.size
    assert width == grant_width
    assert height == grant_height


def test_jpeg_metadata_preserved_through_crop(user, jpeg_image_post, s3_uploads_client):
    # get the original exif tags
    path = jpeg_image_post.get_image_path(image_size.NATIVE)
    image = Image.open(s3_uploads_client.get_object_data_stream(path))
    exif_data = image.info['exif']
    assert exif_data

    # crop the image
    jpeg_image_post.image_item['crop'] = {'upperLeft': {'x': 8, 'y': 8}, 'lowerRight': {'x': 64, 'y': 64}}
    jpeg_image_post.crop_native_jpeg_cache()

    # check the image dimensions have changed, but the exif data has not
    image = jpeg_image_post.native_jpeg_cache.get_image()
    assert image.size[0] != grant_width
    assert image.size[1] != grant_width
    assert image.info['exif'] == exif_data


def test_cached_native_jpeg_cache_dirty_after_crop(user, jpeg_image_post, s3_uploads_client):
    # crop the image, check there is no cached data right after
    jpeg_image_post.image_item['crop'] = {'upperLeft': {'x': 8, 'y': 8}, 'lowerRight': {'x': 64, 'y': 64}}
    jpeg_image_post.crop_native_jpeg_cache()
    assert jpeg_image_post.native_jpeg_cache.is_dirty
