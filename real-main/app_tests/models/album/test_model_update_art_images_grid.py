from os import path
import random
from uuid import uuid4

import pytest

from app.models.media.enums import MediaSize, MediaStatus

# valid jpegs with different aspect ratios
grant_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'grant.jpg')
grant_horz_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'grant-horizontal.jpg')
grant_vert_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'grant-vertical.jpg')


@pytest.fixture
def user(user_manager):
    yield user_manager.create_cognito_only_user('uid', 'uname')


@pytest.fixture
def album(album_manager, user):
    yield album_manager.add_album(user.id, 'aid', 'album name')


@pytest.fixture
def post1(post_manager, user):
    post = post_manager.add_post(user.id, str(uuid4()), media_uploads=[{'mediaId': str(uuid4())}])
    media = post_manager.media_manager.init_media(post.item['mediaObjects'][0])
    image_path = random.choice([grant_path, grant_horz_path, grant_vert_path])
    for size in MediaSize._ALL:
        path = media.get_s3_path(size)
        post_manager.clients['s3_uploads'].put_object(path, open(image_path, 'rb'), 'application/octet-stream')
    media.set_status(MediaStatus.UPLOADED)
    media.set_checksum()
    post.complete()
    yield post


post2 = post1
post3 = post1
post4 = post1
post5 = post1
post6 = post1
post7 = post1
post8 = post1
post9 = post1
post10 = post1
post11 = post1
post12 = post1
post13 = post1
post14 = post1
post15 = post1
post16 = post1


def test_cannot_update_album_art_images_grid_with_non_square_number_of_posts(album):
    art_hash = 'whateves'
    for i in [0, 2, 3, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 17, 18, 19, 20]:
        with pytest.raises(AssertionError):
            album.update_art_images_grid(art_hash, list(range(i)))


def test_cannot_update_album_art_images_grid_with_one_post(album):
    art_hash = 'whateves'
    with pytest.raises(AssertionError):
        album.update_art_images_grid(art_hash, ['a'])


def test_update_album_art_images_grid(album, post1, post2, post3, post4, post5, post6, post7, post8, post9, post10,
                                      post11, post12, post13, post14, post15, post16, s3_client):
    # check no no art for album
    assert 'artHash' not in album.item
    for size in MediaSize._ALL:
        assert album.get_art_image_path(size) is None

    # set to 2x2 grid
    art_hash_4 = '4'
    post_ids_4 = [post1.id, post2.id, post3.id, post4.id]
    album.update_art_images_grid(art_hash_4, post_ids_4)

    # check that update went through correctly
    art_hash_4_paths = {
        size: album.get_art_image_path(size, art_hash=art_hash_4)
        for size in MediaSize._ALL
    }
    art_hash_4_datas = {
        size: s3_client.get_object_data_stream(art_path).read()
        for size, art_path in art_hash_4_paths.items()
    }
    for size in MediaSize._ALL:
        assert art_hash_4_paths[size]
        assert art_hash_4_datas[size]
        # uncomment to write these out to disk for manual inspection
        # with open(f'out4_{size}.jpg', 'wb') as fh:
        #     fh.write(art_hash_4_datas[size])

    # set to 3x3 grid
    art_hash_9 = '9'
    post_ids_9 = post_ids_4 + [post5.id, post6.id, post7.id, post8.id, post9.id]
    album.update_art_images_grid(art_hash_9, post_ids_9)

    # check that update went through correctly
    art_hash_9_paths = {
        size: album.get_art_image_path(size, art_hash=art_hash_9)
        for size in MediaSize._ALL
    }
    art_hash_9_datas = {
        size: s3_client.get_object_data_stream(art_path).read()
        for size, art_path in art_hash_9_paths.items()
    }
    for size in MediaSize._ALL:
        assert art_hash_9_paths[size]
        assert art_hash_9_paths[size] != art_hash_4_paths[size]
        assert art_hash_9_datas[size]
        assert art_hash_9_datas[size] != art_hash_4_datas[size]
        # uncomment to write these out to disk for manual inspection
        # with open(f'out9_{size}.jpg', 'wb') as fh:
        #     fh.write(art_hash_9_datas[size])

    # set to 4x4 grid
    art_hash_16 = '16'
    post_ids_16 = post_ids_9 + [post10.id, post11.id, post12.id, post13.id, post14.id, post15.id, post16.id]
    album.update_art_images_grid(art_hash_16, post_ids_16)

    # check that update went through correctly
    art_hash_16_paths = {
        size: album.get_art_image_path(size, art_hash=art_hash_16)
        for size in MediaSize._ALL
    }
    art_hash_16_datas = {
        size: s3_client.get_object_data_stream(art_path).read()
        for size, art_path in art_hash_16_paths.items()
    }
    for size in MediaSize._ALL:
        assert art_hash_16_paths[size]
        assert art_hash_16_paths[size] != art_hash_4_paths[size]
        assert art_hash_16_paths[size] != art_hash_9_paths[size]
        assert art_hash_16_datas[size]
        assert art_hash_16_datas[size] != art_hash_4_datas[size]
        assert art_hash_16_datas[size] != art_hash_9_datas[size]
        # uncomment to write these out to disk for manual inspection
        # with open(f'out16_{size}.jpg', 'wb') as fh:
        #     fh.write(art_hash_16_datas[size])
