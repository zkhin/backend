import uuid

import pendulum
import pytest

from app.models.follow.dynamo import FollowDynamo
from app.models.follow.enums import FollowStatus


@pytest.fixture
def follow_dynamo(dynamo_client):
    yield FollowDynamo(dynamo_client)


@pytest.fixture
def user1(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user1
user3 = user1


def test_add_following(follow_dynamo, user1, user2):
    # verify doesn't already exist
    follow_item = follow_dynamo.get_following(user1.id, user2.id)
    assert follow_item is None

    # add it
    follow_status = 'just-a-string-at-this-level'
    follow_item = follow_dynamo.add_following(user1.id, user2.id, follow_status)

    # test it stuck in the db
    assert follow_dynamo.get_following(user1.id, user2.id) == follow_item
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


def test_add_following_timestamp(follow_dynamo, user1, user2):
    # timestamp is set when the query is compiled, not executed
    before = pendulum.now('utc')
    follow_item = follow_dynamo.add_following(user1.id, user2.id, FollowStatus.FOLLOWING)
    after = pendulum.now('utc')

    assert follow_dynamo.get_following(user1.id, user2.id) == follow_item
    assert before < pendulum.parse(follow_item['followedAt']) < after


def test_add_following_already_exists(follow_dynamo, user1, user2):
    # add it
    follow_dynamo.add_following(user1.id, user2.id, FollowStatus.FOLLOWING)

    # try to add it again
    with pytest.raises(follow_dynamo.client.exceptions.ConditionalCheckFailedException):
        follow_dynamo.add_following(user1.id, user2.id, FollowStatus.FOLLOWING)


def test_update_following_status(follow_dynamo, user1, user2):
    first_status = 'first'
    second_status = 'second'

    # add it, verify it has the first status
    old_follow_item = follow_dynamo.add_following(user1.id, user2.id, first_status)
    assert follow_dynamo.get_following(user1.id, user2.id) == old_follow_item
    assert old_follow_item['followStatus'] == first_status

    # change it verify it has the second status in the right places
    new_follow_item = follow_dynamo.update_following_status(old_follow_item, second_status)
    assert follow_dynamo.get_following(user1.id, user2.id) == new_follow_item
    assert new_follow_item['followStatus'] == second_status
    assert new_follow_item['gsiA1SortKey'].startswith(second_status + '/')
    assert new_follow_item['gsiA2SortKey'].startswith(second_status + '/')

    # verify nothing else changed
    new_follow_item['followStatus'] = first_status
    new_follow_item['gsiA1SortKey'] = '/'.join([first_status, new_follow_item['gsiA1SortKey'].split('/')[1]])
    new_follow_item['gsiA2SortKey'] = '/'.join([first_status, new_follow_item['gsiA2SortKey'].split('/')[1]])
    assert new_follow_item == old_follow_item


def test_update_following_status_doesnt_exist(follow_dynamo, user1, user2):
    dummy_follow_item = {
        'partitionKey': f'following/{user1.id}/{user2.id}',
        'sortKey': '-',
        'followedAt': pendulum.now('utc').to_iso8601_string(),
    }
    with pytest.raises(follow_dynamo.client.exceptions.ConditionalCheckFailedException):
        follow_dynamo.update_following_status(dummy_follow_item, 'status')


def test_delete_following(follow_dynamo, user1, user2):
    # add it, verify
    follow_item = follow_dynamo.add_following(user1.id, user2.id, 'status')
    assert follow_dynamo.get_following(user1.id, user2.id) == follow_item

    # delete it, verify
    follow_dynamo.delete_following(follow_item)
    assert follow_dynamo.get_following(user1.id, user2.id) is None


def test_delete_following_doesnt_exist(follow_dynamo, user1, user2):
    dummy_follow_item = {
        'partitionKey': f'following/{user1.id}/{user2.id}',
        'sortKey': '-',
    }
    assert follow_dynamo.delete_following(dummy_follow_item) is None


def test_generate_followers(follow_dynamo, user1, user2, user3):
    our_user = user1
    other1_user = user2
    other2_user = user3

    # check we have no followers
    resp = list(follow_dynamo.generate_follower_items(our_user.id))
    assert len(resp) == 0

    # one user follows us, check our generated followers
    follow_dynamo.add_following(other1_user.id, our_user.id, 'anything')
    resp = list(follow_dynamo.generate_follower_items(our_user.id))
    assert len(resp) == 1
    assert resp[0]['followerUserId'] == other1_user.id
    assert resp[0]['followedUserId'] == our_user.id

    # the other user follows us, check our generated followers
    follow_dynamo.add_following(other2_user.id, our_user.id, 'anything')
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
    follow_dynamo.add_following(our_user.id, other1_user.id, 'anything')
    resp = list(follow_dynamo.generate_followed_items(our_user.id))
    assert len(resp) == 1
    assert resp[0]['followerUserId'] == our_user.id
    assert resp[0]['followedUserId'] == other1_user.id

    # we follow the other user, check our generated followeds
    follow_dynamo.add_following(our_user.id, other2_user.id, 'anything')
    resp = list(follow_dynamo.generate_followed_items(our_user.id))
    assert len(resp) == 2
    assert resp[0]['followerUserId'] == our_user.id
    assert resp[0]['followedUserId'] == other1_user.id
    assert resp[1]['followerUserId'] == our_user.id
    assert resp[1]['followedUserId'] == other2_user.id
