import pytest

from app.models.followed_first_story.dynamo import FollowedFirstStoryDynamo


@pytest.fixture
def ffs_dynamo(dynamo_client):
    yield FollowedFirstStoryDynamo(dynamo_client)


@pytest.fixture
def story():
    yield {
        'postId': 'pid',
        'postedByUserId': 'pb-uid',
        'expiresAt': 'e-at',
        'postedAt': 'p-at',
    }


def test_set_all_no_followers(ffs_dynamo, story):
    ffs_dynamo.set_all([], story)
    # check no items were added to the db
    resp = ffs_dynamo.client.table.scan()
    assert resp['Count'] == 0


def test_delete_all_no_followers(ffs_dynamo, story):
    ffs_dynamo.delete_all([], story['postedByUserId'])
    # check no items were added to the db
    resp = ffs_dynamo.client.table.scan()
    assert resp['Count'] == 0


def test_set_correct_format(ffs_dynamo, story):
    follower_user_ids = ['f-uid']
    ffs_dynamo.set_all(follower_user_ids, story)

    # get that one item from the db
    resp = ffs_dynamo.client.table.scan()
    assert resp['Count'] == 1
    item = resp['Items'][0]
    assert item == {
        'schemaVersion': 1,
        'partitionKey': 'followedFirstStory/f-uid/pb-uid',
        'sortKey': '-',
        'gsiA1PartitionKey': 'followedFirstStory/f-uid',
        'gsiA1SortKey': 'e-at',
        'postedByUserId': 'pb-uid',
        'postId': 'pid',
        'postedAt': 'p-at',
        'expiresAt': 'e-at',
    }


def test_set_all_and_delete_all_max_size(ffs_dynamo, story):
    with pytest.raises(AssertionError):
        ffs_dynamo.set_all(range(0, 26), story)

    with pytest.raises(AssertionError):
        ffs_dynamo.delete_all(range(0, 26), story)


def test_set_all_and_delete_all(ffs_dynamo, story):
    # check we start with nothing in DB
    resp = ffs_dynamo.client.table.scan()
    assert resp['Count'] == 0

    # put two items in the DB, make sure they got there correctly
    follower_user_ids = ['f-uid-2', 'f-uid-3']
    ffs_dynamo.set_all(follower_user_ids, story)
    resp = ffs_dynamo.client.table.scan()
    assert resp['Count'] == 2
    pks = sorted(map(lambda item: item['partitionKey'], resp['Items']))
    assert pks == ['followedFirstStory/f-uid-2/pb-uid', 'followedFirstStory/f-uid-3/pb-uid']

    # put another item in the DB, check DB again
    follower_user_ids = ['f-uid-1']
    ffs_dynamo.set_all(follower_user_ids, story)
    resp = ffs_dynamo.client.table.scan()
    assert resp['Count'] == 3
    pks = sorted(map(lambda item: item['partitionKey'], resp['Items']))
    assert pks == [
        'followedFirstStory/f-uid-1/pb-uid',
        'followedFirstStory/f-uid-2/pb-uid',
        'followedFirstStory/f-uid-3/pb-uid',
    ]

    # delete two items from the DB, check
    follower_user_ids = ['f-uid-1', 'f-uid-3']
    ffs_dynamo.delete_all(follower_user_ids, story['postedByUserId'])
    resp = ffs_dynamo.client.table.scan()
    assert resp['Count'] == 1
    pks = sorted(map(lambda item: item['partitionKey'], resp['Items']))
    assert pks == ['followedFirstStory/f-uid-2/pb-uid']

    # delete remaing item from the DB, check
    follower_user_ids = ['f-uid-2']
    ffs_dynamo.delete_all(follower_user_ids, story['postedByUserId'])
    resp = ffs_dynamo.client.table.scan()
    assert resp['Count'] == 0
