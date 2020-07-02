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
    ffs_dynamo.set_all((uid for uid in []), story)
    # check no items were added to the db
    resp = ffs_dynamo.client.table.scan()
    assert resp['Count'] == 0


def test_delete_all_no_followers(ffs_dynamo, story):
    ffs_dynamo.delete_all((uid for uid in []), story['postedByUserId'])
    # check no items were added to the db
    resp = ffs_dynamo.client.table.scan()
    assert resp['Count'] == 0


def test_set_correct_format(ffs_dynamo, story):
    ffs_dynamo.set_all((uid for uid in ['f-uid']), story)

    # get that one item from the db
    resp = ffs_dynamo.client.table.scan()
    assert resp['Count'] == 1
    item = resp['Items'][0]
    assert item == {
        'schemaVersion': 1,
        'partitionKey': 'user/pb-uid',
        'sortKey': 'follower/f-uid/firstStory',
        'gsiA2PartitionKey': 'follower/f-uid/firstStory',
        'gsiA2SortKey': 'e-at',
        'postId': 'pid',
    }


def test_set_all_and_delete_all(ffs_dynamo, story):
    # check we start with nothing in DB
    resp = ffs_dynamo.client.table.scan()
    assert resp['Count'] == 0

    # put two items in the DB, make sure they got there correctly
    ffs_dynamo.set_all((uid for uid in ['f-uid-2', 'f-uid-3']), story)
    resp = ffs_dynamo.client.table.scan()
    assert resp['Count'] == 2
    assert all(item['partitionKey'] == 'user/pb-uid' for item in resp['Items'])
    sks = sorted(map(lambda item: item['sortKey'], resp['Items']))
    assert sks == ['follower/f-uid-2/firstStory', 'follower/f-uid-3/firstStory']

    # put another item in the DB, check DB again
    ffs_dynamo.set_all((uid for uid in ['f-uid-1']), story)
    resp = ffs_dynamo.client.table.scan()
    assert resp['Count'] == 3
    assert all(item['partitionKey'] == 'user/pb-uid' for item in resp['Items'])
    sks = sorted(map(lambda item: item['sortKey'], resp['Items']))
    assert sks == [
        'follower/f-uid-1/firstStory',
        'follower/f-uid-2/firstStory',
        'follower/f-uid-3/firstStory',
    ]

    # delete two items from the DB, check
    ffs_dynamo.delete_all((uid for uid in ['f-uid-1', 'f-uid-3']), story['postedByUserId'])
    resp = ffs_dynamo.client.table.scan()
    assert resp['Count'] == 1
    assert all(item['partitionKey'] == 'user/pb-uid' for item in resp['Items'])
    sks = sorted(map(lambda item: item['sortKey'], resp['Items']))
    assert sks == ['follower/f-uid-2/firstStory']

    # delete remaing item from the DB, check
    ffs_dynamo.delete_all((uid for uid in ['f-uid-2']), story['postedByUserId'])
    resp = ffs_dynamo.client.table.scan()
    assert resp['Count'] == 0
