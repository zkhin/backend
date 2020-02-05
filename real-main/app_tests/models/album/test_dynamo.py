import pendulum
import pytest

from app.models.album.dynamo import AlbumDynamo


@pytest.fixture
def album_dynamo(dynamo_client):
    yield AlbumDynamo(dynamo_client)


@pytest.fixture
def album_item(album_dynamo):
    album_id = 'aid'
    transact = album_dynamo.transact_add_album(album_id, 'uid', 'album name')
    album_dynamo.client.transact_write_items([transact])
    yield album_dynamo.get_album(album_id)


def test_transact_add_album_minimal(album_dynamo):
    album_id = 'aid'
    user_id = 'uid'
    name = 'aname'

    # add the album to the DB
    before_str = pendulum.now('utc').to_iso8601_string()
    transact = album_dynamo.transact_add_album(album_id, user_id, name)
    after_str = pendulum.now('utc').to_iso8601_string()
    album_dynamo.client.transact_write_items([transact])

    # retrieve the album and verify the format is as we expect
    album_item = album_dynamo.get_album(album_id)
    created_at_str = album_item['createdAt']
    assert before_str <= created_at_str
    assert after_str >= created_at_str
    assert album_item == {
        'partitionKey': 'album/aid',
        'sortKey': '-',
        'schemaVersion': 0,
        'gsiA1PartitionKey': 'album/uid',
        'gsiA1SortKey': created_at_str,
        'albumId': 'aid',
        'ownedByUserId': 'uid',
        'createdAt': created_at_str,
        'name': 'aname',
    }


def test_transact_add_album_maximal(album_dynamo):
    album_id = 'aid'
    user_id = 'uid'
    name = 'aname'
    description = 'adesc'

    # add the album to the DB
    created_at = pendulum.now('utc')
    album_dynamo.client.transact_write_items([
        album_dynamo.transact_add_album(album_id, user_id, name, description=description, created_at=created_at),
    ])

    # retrieve the album and verify the format is as we expect
    album_item = album_dynamo.get_album(album_id)
    created_at_str = created_at.to_iso8601_string()
    assert album_item == {
        'partitionKey': 'album/aid',
        'sortKey': '-',
        'schemaVersion': 0,
        'gsiA1PartitionKey': 'album/uid',
        'gsiA1SortKey': created_at_str,
        'albumId': 'aid',
        'ownedByUserId': 'uid',
        'createdAt': created_at_str,
        'name': 'aname',
        'description': 'adesc',
    }


def test_cant_transact_add_album_same_album_id(album_dynamo, album_item):
    album_id = album_item['albumId']

    # verify we can't add another album with the same id
    transact = album_dynamo.transact_add_album(album_id, 'uid2', 'n2')
    with pytest.raises(album_dynamo.client.boto3_client.exceptions.ConditionalCheckFailedException):
        album_dynamo.client.transact_write_items([transact])


def test_set(album_dynamo, album_item):
    album_id = album_item['albumId']

    # check starting state
    assert album_item['name'] != 'new name'
    assert 'description' not in album_item

    # change just name
    album_item = album_dynamo.set(album_id, name='new name')
    assert album_item['name'] == 'new name'
    assert 'description' not in album_item

    # change both name and description
    album_item = album_dynamo.set(album_id, name='newer name', description='new desc')
    assert album_item['name'] == 'newer name'
    assert album_item['description'] == 'new desc'

    # delete the description
    album_item = album_dynamo.set(album_id, description='')
    assert album_item['name'] == 'newer name'
    assert 'description' not in album_item


def test_set_errors(album_dynamo, album_item):
    album_id = album_item['albumId']

    # try to set paramters on album that doesn't exist
    with pytest.raises(album_dynamo.client.exceptions.ConditionalCheckFailedException):
        album_dynamo.set(album_id + '-dne', name='new name')

    # try to set with no parameters
    with pytest.raises(AssertionError):
        album_dynamo.set(album_id)

    # try to remove name
    with pytest.raises(AssertionError):
        album_dynamo.set(album_id, name='')


def test_cant_transact_delete_album_doesnt_exist(album_dynamo):
    album_id = 'dne-cid'
    transact = album_dynamo.transact_delete_album(album_id)
    with pytest.raises(album_dynamo.client.exceptions.ConditionalCheckFailedException):
        album_dynamo.client.transact_write_items([transact])


def test_transact_delete_album(album_dynamo, album_item):
    album_id = album_item['albumId']

    # verify we can see the album in the DB
    album_item = album_dynamo.get_album(album_id)
    assert album_item['albumId'] == album_id

    # delete the album
    transact = album_dynamo.transact_delete_album(album_id)
    album_dynamo.client.transact_write_items([transact])

    # verify the album is no longer in the db
    assert album_dynamo.get_album(album_id) is None


def test_transact_add_post(album_dynamo, album_item):
    album_id = album_item['albumId']
    assert album_item.get('postCount', 0) == 0
    assert 'postsLastUpdatedAt' not in album_item

    # add a post, check the new state
    now = pendulum.now('utc')
    transact = album_dynamo.transact_add_post(album_id, now=now)
    album_dynamo.client.transact_write_items([transact])
    album_item = album_dynamo.get_album(album_id)
    assert album_item.get('postCount', 0) == 1
    assert album_item['postsLastUpdatedAt'] == now.to_iso8601_string()

    # add another post, check the new state
    transact = album_dynamo.transact_add_post(album_id)
    album_dynamo.client.transact_write_items([transact])
    album_item = album_dynamo.get_album(album_id)
    assert album_item.get('postCount', 0) == 2
    assert album_item['postsLastUpdatedAt'] > now.to_iso8601_string()


def test_transact_remove_post(album_dynamo, album_item):
    album_id = album_item['albumId']

    # add a post, check state
    transact = album_dynamo.transact_add_post(album_id)
    album_dynamo.client.transact_write_items([transact])
    album_item = album_dynamo.get_album(album_id)
    assert album_item.get('postCount', 0) == 1
    assert album_item['postsLastUpdatedAt']

    # remove that post, check state
    now = pendulum.now('utc')
    transact = album_dynamo.transact_remove_post(album_id, now=now)
    album_dynamo.client.transact_write_items([transact])
    album_item = album_dynamo.get_album(album_id)
    assert album_item.get('postCount', 0) == 0
    assert album_item['postsLastUpdatedAt'] == now.to_iso8601_string()

    # verify we can't remove another post
    transact = album_dynamo.transact_remove_post(album_id)
    with pytest.raises(album_dynamo.client.boto3_client.exceptions.ConditionalCheckFailedException):
        album_dynamo.client.transact_write_items([transact])


def test_generate_by_user(album_dynamo, album_item):
    album_id = album_item['albumId']
    user_id = album_item['ownedByUserId']

    # test generating for a user with no albums
    assert list(album_dynamo.generate_by_user('other-uid')) == []

    # test generate for user with one album
    album_items = list(album_dynamo.generate_by_user(user_id))
    assert len(album_items) == 1
    assert album_items[0]['albumId'] == album_id

    # add another album for that user
    album_id_2 = 'aid-2'
    transact = album_dynamo.transact_add_album(album_id_2, user_id, 'album name')
    album_dynamo.client.transact_write_items([transact])

    # test generate for user with two albums
    album_items = list(album_dynamo.generate_by_user(user_id))
    assert len(album_items) == 2
    assert album_items[0]['albumId'] == album_id
    assert album_items[1]['albumId'] == album_id_2
