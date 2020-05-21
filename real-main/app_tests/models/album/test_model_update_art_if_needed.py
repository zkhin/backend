import base64
import decimal
import os.path as path
import uuid

import pytest

from app.models.post.enums import PostType
from app.utils import image_size

# valid jpegs with different aspect ratios
grant_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'grant.jpg')
grant_horz_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'grant-horizontal.jpg')
grant_vert_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'grant-vertical.jpg')


@pytest.fixture
def user(user_manager, cognito_client):
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username='uid')
    yield user_manager.create_cognito_only_user('uid', 'uname')


@pytest.fixture
def album(album_manager, user):
    yield album_manager.add_album(user.id, 'aid', 'album name')


@pytest.fixture
def post1(post_manager, user):
    with open(grant_path, 'rb') as fh:
        image_data = base64.b64encode(fh.read())
    yield post_manager.add_post(user, str(uuid.uuid4()), PostType.IMAGE, image_input={'imageData': image_data})


@pytest.fixture
def post2(post_manager, user):
    with open(grant_horz_path, 'rb') as fh:
        image_data = base64.b64encode(fh.read())
    yield post_manager.add_post(user, str(uuid.uuid4()), PostType.IMAGE, image_input={'imageData': image_data})


@pytest.fixture
def post3(post_manager, user):
    with open(grant_vert_path, 'rb') as fh:
        image_data = base64.b64encode(fh.read())
    yield post_manager.add_post(user, str(uuid.uuid4()), PostType.IMAGE, image_input={'imageData': image_data})


@pytest.fixture
def post4(post_manager, user):
    yield post_manager.add_post(user, str(uuid.uuid4()), PostType.TEXT_ONLY, text='lore ipsum')


post5 = post1
post6 = post2
post7 = post3
post8 = post4
post9 = post1
post10 = post2
post11 = post3
post12 = post4
post13 = post1
post14 = post2
post15 = post3
post16 = post4


def test_update_art_if_needed_no_change_no_posts(album):
    assert 'artHash' not in album.item

    # do the update, check nothing changed
    album.update_art_if_needed()
    assert 'artHash' not in album.item

    # double check nothing changed
    album.refresh_item()
    assert 'artHash' not in album.item


def test_update_art_if_needed_add_change_and_remove_one_post(album, post1, s3_uploads_client):
    assert 'artHash' not in album.item

    # put the post in the album directly in dynamo
    transacts = [post1.dynamo.transact_set_album_id(post1.item, album.id, album_rank=0)]
    post1.dynamo.client.transact_write_items(transacts)

    # update art
    album.update_art_if_needed()
    art_hash = album.item['artHash']
    assert art_hash

    # check all art sizes are in S3, native image is correct
    for size in image_size.JPEGS:
        path = album.get_art_image_path(size)
        assert album.s3_uploads_client.exists(path)
    native_path = album.get_art_image_path(image_size.NATIVE)
    assert s3_uploads_client.get_object_data_stream(native_path).read() == post1.k4_jpeg_cache.get_fh().read()

    # remove the post from the album directly in dynamo
    transacts = [post1.dynamo.transact_set_album_id(post1.item, None)]
    post1.dynamo.client.transact_write_items(transacts)

    # update art
    album.update_art_if_needed()
    assert 'artHash' not in album.item

    # check all art sizes were removed from S3
    for size in image_size.JPEGS:
        path = album.get_art_image_path(size, art_hash=art_hash)
        assert not album.s3_uploads_client.exists(path)


def test_changing_post_rank_changes_art(album, post1, post2, s3_uploads_client):
    assert 'artHash' not in album.item

    # put the post in the album directly in dynamo
    transacts = [post1.dynamo.transact_set_album_id(post1.item, album.id, album_rank=0.5)]
    post1.dynamo.client.transact_write_items(transacts)

    # update art
    album.update_art_if_needed()
    first_art_hash = album.item['artHash']
    assert first_art_hash

    # check the native art matches first post
    native_path = album.get_art_image_path(image_size.NATIVE)
    assert s3_uploads_client.get_object_data_stream(native_path).read() == post1.k4_jpeg_cache.get_fh().read()

    # put the other post in the album directly, ahead of the firs
    transacts = [post2.dynamo.transact_set_album_id(post2.item, album.id, album_rank=decimal.Decimal('0.2'))]
    post2.dynamo.client.transact_write_items(transacts)

    # update art
    album.update_art_if_needed()
    second_art_hash = album.item['artHash']
    assert second_art_hash != first_art_hash

    # check the native art now matches second post
    native_path = album.get_art_image_path(image_size.NATIVE)
    assert s3_uploads_client.get_object_data_stream(native_path).read() == post2.k4_jpeg_cache.get_fh().read()

    # now switch order, directly in dynsmo
    transacts = [post1.dynamo.transact_set_album_rank(post1.id, decimal.Decimal('0.1'))]
    post1.dynamo.client.transact_write_items(transacts)

    # update art
    album.update_art_if_needed()
    third_art_hash = album.item['artHash']
    assert third_art_hash != second_art_hash
    assert third_art_hash == first_art_hash

    # check the native art now matches first post
    native_path = album.get_art_image_path(image_size.NATIVE)
    assert s3_uploads_client.get_object_data_stream(native_path).read() == post1.k4_jpeg_cache.get_fh().read()

    # check the thumbnails are all in S3, and all the old thumbs have been removed
    for size in image_size.JPEGS:
        path = album.get_art_image_path(size)
        old_path = album.get_art_image_path(size, art_hash=second_art_hash)
        assert s3_uploads_client.exists(path)
        assert not s3_uploads_client.exists(old_path)


def test_1_4_9_16_posts_in_album(album, post1, post2, post3, post4, post5, post6, post7, post8, post9, post10,
                                 post11, post12, post13, post14, post15, post16):
    assert 'artHash' not in album.item
    post_dynamo = post1.dynamo

    # put the first post in the album directly in dynamo
    transacts = [post_dynamo.transact_set_album_id(post1.item, album.id, album_rank=0)]
    post_dynamo.client.transact_write_items(transacts)

    # update art
    album.update_art_if_needed()
    first_art_hash = album.item['artHash']
    assert first_art_hash

    # check the native art matches first post
    native_path = album.get_art_image_path(image_size.NATIVE)
    first_native_image_data = album.s3_uploads_client.get_object_data_stream(native_path).read()
    assert first_native_image_data == post1.k4_jpeg_cache.get_fh().read()

    # add three more posts to the album
    transacts = [
        post_dynamo.transact_set_album_id(post2.item, album.id, album_rank=decimal.Decimal('0.05')),
        post_dynamo.transact_set_album_id(post3.item, album.id, album_rank=decimal.Decimal('0.10')),
        post_dynamo.transact_set_album_id(post4.item, album.id, album_rank=decimal.Decimal('0.15')),
    ]
    post_dynamo.client.transact_write_items(transacts)

    # update art
    album.update_art_if_needed()
    fourth_art_hash = album.item['artHash']
    assert fourth_art_hash != first_art_hash

    # check the native art has changed
    native_path = album.get_art_image_path(image_size.NATIVE)
    fourth_native_image_data = album.s3_uploads_client.get_object_data_stream(native_path).read()
    assert fourth_native_image_data != first_native_image_data

    # add 5th thru 9th posts to the album
    transacts = [
        post_dynamo.transact_set_album_id(post5.item, album.id, album_rank=decimal.Decimal('0.20')),
        post_dynamo.transact_set_album_id(post6.item, album.id, album_rank=decimal.Decimal('0.25')),
        post_dynamo.transact_set_album_id(post6.item, album.id, album_rank=decimal.Decimal('0.30')),
        post_dynamo.transact_set_album_id(post7.item, album.id, album_rank=decimal.Decimal('0.35')),
        post_dynamo.transact_set_album_id(post8.item, album.id, album_rank=decimal.Decimal('0.40')),
        post_dynamo.transact_set_album_id(post9.item, album.id, album_rank=decimal.Decimal('0.45')),
    ]
    post_dynamo.client.transact_write_items(transacts)

    # update art
    album.update_art_if_needed()
    nineth_art_hash = album.item['artHash']
    assert nineth_art_hash != fourth_art_hash

    # check the native art has changed
    native_path = album.get_art_image_path(image_size.NATIVE)
    nineth_native_image_data = album.s3_uploads_client.get_object_data_stream(native_path).read()
    assert nineth_native_image_data != fourth_native_image_data

    # add 10th thru 16th posts to the album
    transacts = [
        post_dynamo.transact_set_album_id(post10.item, album.id, album_rank=decimal.Decimal('0.50')),
        post_dynamo.transact_set_album_id(post11.item, album.id, album_rank=decimal.Decimal('0.55')),
        post_dynamo.transact_set_album_id(post12.item, album.id, album_rank=decimal.Decimal('0.60')),
        post_dynamo.transact_set_album_id(post13.item, album.id, album_rank=decimal.Decimal('0.65')),
        post_dynamo.transact_set_album_id(post14.item, album.id, album_rank=decimal.Decimal('0.70')),
        post_dynamo.transact_set_album_id(post15.item, album.id, album_rank=decimal.Decimal('0.75')),
        post_dynamo.transact_set_album_id(post16.item, album.id, album_rank=decimal.Decimal('0.80')),
    ]
    post_dynamo.client.transact_write_items(transacts)

    # update art
    album.update_art_if_needed()
    sixteenth_art_hash = album.item['artHash']
    assert sixteenth_art_hash != nineth_art_hash

    # check the native art has changed
    native_path = album.get_art_image_path(image_size.NATIVE)
    sixteenth_native_image_data = album.s3_uploads_client.get_object_data_stream(native_path).read()
    assert sixteenth_native_image_data != nineth_native_image_data
