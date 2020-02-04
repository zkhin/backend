from datetime import datetime

import pytest

from app.models.flag.dynamo import FlagDynamo


@pytest.fixture
def flag_dynamo(dynamo_client):
    yield FlagDynamo(dynamo_client)


def test_transact_add_flag(flag_dynamo):
    post_id = 'pid'
    user_id = 'uid'
    now = datetime.utcnow()
    flagged_at_str = now.isoformat() + 'Z'

    # add a flag
    transacts = [flag_dynamo.transact_add_flag(post_id, user_id, now=now)]
    flag_dynamo.client.transact_write_items(transacts)

    # check flag item has right form
    flag_item = flag_dynamo.get_flag(post_id, user_id)
    assert flag_item == {
        'schemaVersion': 1,
        'partitionKey': 'flag/uid/pid',
        'sortKey': '-',
        'gsiA1PartitionKey': 'flag/uid',
        'gsiA1SortKey': flagged_at_str,
        'gsiA2PartitionKey': 'flag/pid',
        'gsiA2SortKey': flagged_at_str,
        'postId': 'pid',
        'flaggerUserId': 'uid',
        'flaggedAt': flagged_at_str,
    }

    # check we can't re-add same flag item
    with pytest.raises(flag_dynamo.client.boto3_client.exceptions.ConditionalCheckFailedException):
        flag_dynamo.client.transact_write_items(transacts)


def test_transact_delete_flag(flag_dynamo):
    post_id = 'pid'
    user_id = 'uid'

    # add a flag, verify it's there
    transacts = [flag_dynamo.transact_add_flag(post_id, user_id)]
    flag_dynamo.client.transact_write_items(transacts)
    assert flag_dynamo.get_flag(post_id, user_id) is not None

    # delete the flag, verify it disappeared
    transacts = [flag_dynamo.transact_delete_flag(post_id, user_id)]
    flag_dynamo.client.transact_write_items(transacts)
    assert flag_dynamo.get_flag(post_id, user_id) is None


def test_transact_delete_flag_doesnt_exist(flag_dynamo):
    # check we can't delete the flag now that it doesn't exist
    transacts = [flag_dynamo.transact_delete_flag('pid', 'uid')]
    with pytest.raises(flag_dynamo.client.boto3_client.exceptions.ConditionalCheckFailedException):
        flag_dynamo.client.transact_write_items(transacts)


def test_generate_flag_items_by_user(flag_dynamo):
    user_id = 'uid'

    # test generate no items
    assert list(flag_dynamo.generate_flag_items_by_user(user_id)) == []

    # add two flags for this user
    post_id_1, post_id_2 = 'pid1', 'pid2'
    transacts = [
        flag_dynamo.transact_add_flag(post_id_1, user_id),
        flag_dynamo.transact_add_flag(post_id_2, user_id),
    ]
    flag_dynamo.client.transact_write_items(transacts)

    # verify we can generate those flags
    flag_items = list(flag_dynamo.generate_flag_items_by_user(user_id))
    assert len(flag_items) == 2
    assert post_id_1 in [f['postId'] for f in flag_items]
    assert post_id_2 in [f['postId'] for f in flag_items]


def test_generate_flag_items_by_post(flag_dynamo):
    post_id = 'pid'

    # test generate no items
    assert list(flag_dynamo.generate_flag_items_by_post(post_id)) == []

    # add two flags on this post
    user_id_1, user_id_2 = 'uid1', 'uid2'
    transacts = [
        flag_dynamo.transact_add_flag(post_id, user_id_1),
        flag_dynamo.transact_add_flag(post_id, user_id_2),
    ]
    flag_dynamo.client.transact_write_items(transacts)

    # verify we can generate those flags
    flag_items = list(flag_dynamo.generate_flag_items_by_post(post_id))
    assert len(flag_items) == 2
    assert user_id_1 in [f['flaggerUserId'] for f in flag_items]
    assert user_id_2 in [f['flaggerUserId'] for f in flag_items]
