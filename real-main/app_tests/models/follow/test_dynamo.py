import pendulum
import pytest

from app.models.follow.enums import FollowStatus
from app.models.follow.dynamo import FollowDynamo


@pytest.fixture
def follow_dynamo(dynamo_client):
    yield FollowDynamo(dynamo_client)


@pytest.fixture
def user1(user_manager):
    yield user_manager.create_cognito_only_user('uid1', 'uname1')


@pytest.fixture
def user2(user_manager):
    yield user_manager.create_cognito_only_user('uid2', 'uname2')


@pytest.fixture
def user3(user_manager):
    yield user_manager.create_cognito_only_user('uid3', 'uname3')


def test_transact_add_following(follow_dynamo, user1, user2):
    # verify doesn't already exist
    follow_item = follow_dynamo.get_following(user1.id, user2.id)
    assert follow_item is None

    # add it
    follow_status = 'just-a-string-at-this-level'
    transact = follow_dynamo.transact_add_following(user1.id, user2.id, follow_status)
    follow_dynamo.client.transact_write_items([transact])

    # test it stuck in the db
    follow_item = follow_dynamo.get_following(user1.id, user2.id)
    followed_at_str = follow_item['followedAt']
    assert follow_item == {
        'schemaVersion': 1,
        'partitionKey': f'following/{user1.id}/{user2.id}',
        'sortKey': '-',
        'gsiA1PartitionKey': f'follower/{user1.id}',
        'gsiA1SortKey': f'{follow_status}/{followed_at_str}',
        'gsiA2PartitionKey': f'followed/{user2.id}',
        'gsiA2SortKey': f'{follow_status}/{followed_at_str}',
        'followStatus': follow_status,
        'followedAt': followed_at_str,
        'followerUserId': user1.id,
        'followedUserId': user2.id,
    }


def test_transact_add_following_timestamp(follow_dynamo, user1, user2):
    # timestamp is set when the query is compiled, not executed
    before = pendulum.now('utc')
    transact = follow_dynamo.transact_add_following(user1.id, user2.id, FollowStatus.FOLLOWING)
    after = pendulum.now('utc')

    follow_dynamo.client.transact_write_items([transact])
    follow_item = follow_dynamo.get_following(user1.id, user2.id)
    followed_at = pendulum.parse(follow_item['followedAt'])

    assert followed_at > before
    assert followed_at < after


def test_transact_add_following_already_exists(follow_dynamo, user1, user2):
    # add it
    transact = follow_dynamo.transact_add_following(user1.id, user2.id, FollowStatus.FOLLOWING)
    follow_dynamo.client.transact_write_items([transact])

    # try to add it again
    with pytest.raises(follow_dynamo.client.exceptions.ConditionalCheckFailedException):
        follow_dynamo.client.transact_write_items([transact])


def test_transact_update_following_status(follow_dynamo, user1, user2):
    first_status = 'first'
    second_status = 'second'

    # add it, verify it has the first status
    transact = follow_dynamo.transact_add_following(user1.id, user2.id, first_status)
    follow_dynamo.client.transact_write_items([transact])
    old_follow_item = follow_dynamo.get_following(user1.id, user2.id)
    assert old_follow_item['followStatus'] == first_status

    # change it verify it has the second status in the right places
    transact = follow_dynamo.transact_update_following_status(old_follow_item, second_status)
    follow_dynamo.client.transact_write_items([transact])
    new_follow_item = follow_dynamo.get_following(user1.id, user2.id)
    assert new_follow_item['followStatus'] == second_status
    assert new_follow_item['gsiA1SortKey'].startswith(second_status + '/')
    assert new_follow_item['gsiA2SortKey'].startswith(second_status + '/')

    # verify nothing else changed
    new_follow_item['followStatus'] = first_status
    new_follow_item['gsiA1SortKey'] = '/'.join([first_status, new_follow_item['gsiA1SortKey'].split('/')[1]])
    new_follow_item['gsiA2SortKey'] = '/'.join([first_status, new_follow_item['gsiA2SortKey'].split('/')[1]])
    assert new_follow_item == old_follow_item


def test_transact_update_following_status_doesnt_exist(follow_dynamo, user1, user2):
    dummy_follow_item = {
        'partitionKey': f'following/{user1.id}/{user2.id}',
        'sortKey': '-',
        'followedAt': pendulum.now('utc').to_iso8601_string()
    }
    transact = follow_dynamo.transact_update_following_status(dummy_follow_item, 'status')
    with pytest.raises(follow_dynamo.client.exceptions.ConditionalCheckFailedException):
        follow_dynamo.client.transact_write_items([transact])


def test_transact_delete_following(follow_dynamo, user1, user2):
    # add it
    transact = follow_dynamo.transact_add_following(user1.id, user2.id, 'status')
    follow_dynamo.client.transact_write_items([transact])
    follow_item = follow_dynamo.get_following(user1.id, user2.id)
    assert follow_item is not None

    # delete it
    transact = follow_dynamo.transact_delete_following(follow_item)
    follow_dynamo.client.transact_write_items([transact])

    # verify it's gone
    follow_item = follow_dynamo.get_following(user1.id, user2.id)
    assert follow_item is None


def test_transact_delete_following_doesnt_exist(follow_dynamo, user1, user2):
    dummy_follow_item = {
        'partitionKey': f'following/{user1.id}/{user2.id}',
        'sortKey': '-',
    }
    transact = follow_dynamo.transact_delete_following(dummy_follow_item)
    with pytest.raises(follow_dynamo.client.exceptions.ConditionalCheckFailedException):
        follow_dynamo.client.transact_write_items([transact])


def test_generate_followers(follow_dynamo, user1, user2, user3):
    our_user = user1
    other1_user = user2
    other2_user = user3

    # check we have no followers
    resp = list(follow_dynamo.generate_follower_items(our_user.id))
    assert len(resp) == 0

    # one user follows us, check our generated followers
    follow_dynamo.client.transact_write_items([
        follow_dynamo.transact_add_following(other1_user.id, our_user.id, 'anything'),
    ])
    resp = list(follow_dynamo.generate_follower_items(our_user.id))
    assert len(resp) == 1
    assert resp[0]['followerUserId'] == other1_user.id
    assert resp[0]['followedUserId'] == our_user.id

    # the other user follows us, check our generated followers
    follow_dynamo.client.transact_write_items([
        follow_dynamo.transact_add_following(other2_user.id, our_user.id, 'anything'),
    ])
    resp = list(follow_dynamo.generate_follower_items(our_user.id))
    assert len(resp) == 2
    assert resp[0]['followerUserId'] == other1_user.id
    assert resp[0]['followedUserId'] == our_user.id
    assert resp[1]['followerUserId'] == other2_user.id
    assert resp[1]['followedUserId'] == our_user.id


def test_generate_followeds(follow_dynamo, user1, user2, user3):
    our_user = user1
    other1_user = user2
    other2_user = user3

    # check we have no followeds
    resp = list(follow_dynamo.generate_followed_items(our_user.id))
    assert len(resp) == 0

    # we follow another user, check our generated followeds
    follow_dynamo.client.transact_write_items([
        follow_dynamo.transact_add_following(our_user.id, other1_user.id, 'anything'),
    ])
    resp = list(follow_dynamo.generate_followed_items(our_user.id))
    assert len(resp) == 1
    assert resp[0]['followerUserId'] == our_user.id
    assert resp[0]['followedUserId'] == other1_user.id

    # we follow the other user, check our generated followeds
    follow_dynamo.client.transact_write_items([
        follow_dynamo.transact_add_following(our_user.id, other2_user.id, 'anything'),
    ])
    resp = list(follow_dynamo.generate_followed_items(our_user.id))
    assert len(resp) == 2
    assert resp[0]['followerUserId'] == our_user.id
    assert resp[0]['followedUserId'] == other1_user.id
    assert resp[1]['followerUserId'] == our_user.id
    assert resp[1]['followedUserId'] == other2_user.id
