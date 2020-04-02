import logging

import pytest

from migrations.user_5_3_profile_photo_id_post_to_media import Migration

PK_KEYS = ('partitionKey', 'sortKey')


@pytest.fixture
def user_without_photo_media(dynamo_table):
    user_id = 'uid-nm'
    # add to dynamo
    user_item = {
        'partitionKey': f'user/{user_id}',
        'sortKey': 'profile',
        'userId': user_id,
    }
    dynamo_table.put_item(Item=user_item)
    yield user_item


@pytest.fixture
def user_with_photo_media_that_dne(dynamo_table):
    user_id = 'uid-mdne'
    media_id = 'mid-mdne'
    # add to dynamo
    user_item = {
        'partitionKey': f'user/{user_id}',
        'sortKey': 'profile',
        'photoMediaId': f'{media_id}',
        'userId': user_id,
    }
    dynamo_table.put_item(Item=user_item)
    yield user_item


@pytest.fixture
def media(dynamo_table):
    media_id = 'mid-me'
    post_id = 'pid-me'
    # add to dynamo
    media_item = {
        'partitionKey': f'media/{media_id}',
        'sortKey': '-',
        'postId': post_id,
        'mediaId': media_id,
    }
    dynamo_table.put_item(Item=media_item)
    yield media_item


@pytest.fixture
def user_with_photo_media_that_exists(dynamo_table, media):
    user_id = 'uid-me'
    media_id = media['mediaId']
    user_item = {
        'partitionKey': f'user/{user_id}',
        'sortKey': 'profile',
        'photoMediaId': f'{media_id}',
        'userId': user_id,
    }
    dynamo_table.put_item(Item=user_item)
    yield user_item


def test_nothing_to_migrate(dynamo_table, caplog, user_without_photo_media):
    pk = {k: v for k, v in user_without_photo_media.items() if k in PK_KEYS}

    # check starting state in dynamo
    item = dynamo_table.get_item(Key=pk)['Item']
    assert item == user_without_photo_media

    migration = Migration(dynamo_table)
    with caplog.at_level(logging.WARNING):
        migration.run()
    assert len(caplog.records) == 0

    # check no changes
    item = dynamo_table.get_item(Key=pk)['Item']
    assert item == user_without_photo_media


def test_migrate(dynamo_table, caplog, user_with_photo_media_that_dne, user_with_photo_media_that_exists, media):
    user_id_dne = user_with_photo_media_that_dne['userId']
    user_id_exists = user_with_photo_media_that_exists['userId']
    media_id_dne = user_with_photo_media_that_dne['photoMediaId']
    media_id_exists = media['mediaId']
    post_id_exists = media['postId']

    user_pk_media_dne = {k: v for k, v in user_with_photo_media_that_dne.items() if k in PK_KEYS}
    user_pk_media_exists = {k: v for k, v in user_with_photo_media_that_exists.items() if k in PK_KEYS}

    # check starting state dynamo
    item = dynamo_table.get_item(Key=user_pk_media_dne)['Item']
    assert item == user_with_photo_media_that_dne
    item = dynamo_table.get_item(Key=user_pk_media_exists)['Item']
    assert item == user_with_photo_media_that_exists

    # migrate
    migration = Migration(dynamo_table)
    with caplog.at_level(logging.WARNING):
        migration.run()

    # check logging worked
    assert len(caplog.records) == 3
    assert len([r for r in caplog.records if media_id_dne in str(r)]) == 1
    assert len([r for r in caplog.records if media_id_exists in str(r)]) == 0
    assert len([r for r in caplog.records if post_id_exists in str(r)]) == 0
    assert len([r for r in caplog.records if user_id_exists in str(r)]) == 1
    assert len([r for r in caplog.records if user_id_dne in str(r)]) == 2

    # check starting state dynamo
    item = dynamo_table.get_item(Key=user_pk_media_dne)['Item']
    assert item['photoPostId'] == media_id_dne
    assert 'photoMediaId' not in item

    item = dynamo_table.get_item(Key=user_pk_media_exists)['Item']
    assert item['photoPostId'] == post_id_exists
    assert 'photoMediaId' not in item
