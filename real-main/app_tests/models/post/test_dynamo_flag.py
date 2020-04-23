import pendulum
import pytest

from app.models.post.dynamo import PostDynamo, PostFlagDynamo


@pytest.fixture
def post_dynamo(dynamo_client):
    yield PostDynamo(dynamo_client)


@pytest.fixture
def pf_dynamo(dynamo_client):
    yield PostFlagDynamo(dynamo_client)


def test_transact_add(pf_dynamo):
    post_id, user_id = 'pid', 'uid'
    now = pendulum.now('utc')

    # check no flags
    pf_dynamo.get(post_id, user_id) is None

    # flag the post
    transacts = [pf_dynamo.transact_add(post_id, user_id, now=now)]
    pf_dynamo.client.transact_write_items(transacts)

    # check flag item is there and has the correct format
    flag_item = pf_dynamo.get(post_id, user_id)
    assert flag_item == {
        'schemaVersion': 0,
        'partitionKey': 'post/pid',
        'sortKey': 'flag/uid',
        'gsiK1PartitionKey': 'flag/uid',
        'gsiK1SortKey': '-',
        'createdAt': now.to_iso8601_string(),
    }

    # check we can't re-add same flag item
    with pytest.raises(pf_dynamo.client.exceptions.ConditionalCheckFailedException):
        pf_dynamo.client.transact_write_items(transacts)

    # check we can flag without specifying the timestamp
    post_id, user_id = 'pid2', 'uid2'
    before = pendulum.now('utc')
    transacts = [pf_dynamo.transact_add(post_id, user_id)]
    after = pendulum.now('utc')
    pf_dynamo.client.transact_write_items(transacts)

    flag_item = pf_dynamo.get(post_id, user_id)
    created_at = pendulum.parse(flag_item['createdAt'])
    assert created_at >= before
    assert created_at <= after


def test_transact_delete(pf_dynamo):
    post_id, user_id = 'pid', 'uid'

    # flag a post, verify it's really there
    transacts = [pf_dynamo.transact_add(post_id, user_id)]
    pf_dynamo.client.transact_write_items(transacts)
    assert pf_dynamo.get(post_id, user_id)

    # delete the flag, verify it's really gone
    transacts = [pf_dynamo.transact_delete(post_id, user_id)]
    pf_dynamo.client.transact_write_items(transacts)
    assert pf_dynamo.get(post_id, user_id) is None

    # verify we can't delete a post that isn't there
    with pytest.raises(pf_dynamo.client.exceptions.ConditionalCheckFailedException):
        pf_dynamo.client.transact_write_items(transacts)


def test_delete_all_for_post(pf_dynamo, post_dynamo):
    post_id = 'pid'

    # add a related item as a distraction, verify doesn't show up
    post_dynamo.client.transact_write_items([
        post_dynamo.transact_add_pending_post('uid', post_id, 'ptype'),
    ])
    assert list(pf_dynamo.generate_by_post(post_id)) == []

    # test deleting none
    pf_dynamo.delete_all_for_post(post_id)
    assert list(pf_dynamo.generate_by_post(post_id)) == []

    # add two flags to the post
    pf_dynamo.client.transact_write_items([
        pf_dynamo.transact_add(post_id, 'uid'),
        pf_dynamo.transact_add(post_id, 'uid2'),
    ])
    assert len(list(pf_dynamo.generate_by_post(post_id))) == 2

    # test deleting those two
    pf_dynamo.delete_all_for_post(post_id)
    assert list(pf_dynamo.generate_by_post(post_id)) == []


def test_generate_by_post(pf_dynamo):
    post_id = 'pid'

    # add a flag for a different post
    transacts = [pf_dynamo.transact_add('pid-other', 'uid')]
    pf_dynamo.client.transact_write_items(transacts)

    # test generate no items
    assert list(pf_dynamo.generate_by_post(post_id)) == []
    assert list(pf_dynamo.generate_by_post(post_id)) == []

    # add a flag for this post
    transacts = [pf_dynamo.transact_add(post_id, 'uid')]
    pf_dynamo.client.transact_write_items(transacts)

    # test generate one item
    items = list(pf_dynamo.generate_by_post(post_id))
    assert len(items) == 1
    assert items[0]['partitionKey'] == f'post/{post_id}'
    assert items[0]['sortKey'] == 'flag/uid'

    # add another flag for this post
    transacts = [pf_dynamo.transact_add(post_id, 'uid2')]
    pf_dynamo.client.transact_write_items(transacts)

    # test generate two items
    items = list(pf_dynamo.generate_by_post(post_id))
    assert len(items) == 2
    assert items[0]['partitionKey'] == f'post/{post_id}'
    assert items[0]['sortKey'] == 'flag/uid'
    assert items[1]['partitionKey'] == f'post/{post_id}'
    assert items[1]['sortKey'] == 'flag/uid2'

    # check the pks_only flag works
    items = list(pf_dynamo.generate_by_post(post_id, pks_only=True))
    assert len(items) == 2
    assert items[0] == {'partitionKey': f'post/{post_id}', 'sortKey': 'flag/uid'}
    assert items[1] == {'partitionKey': f'post/{post_id}', 'sortKey': 'flag/uid2'}


def test_generate_post_ids_by_user(pf_dynamo):
    user_id = 'uid'

    # add a flag by a different user, test
    transacts = [pf_dynamo.transact_add('pid', 'uid-other')]
    pf_dynamo.client.transact_write_items(transacts)
    assert list(pf_dynamo.generate_post_ids_by_user(user_id)) == []

    # add a flag by this user, test
    transacts = [pf_dynamo.transact_add('pid', user_id)]
    pf_dynamo.client.transact_write_items(transacts)
    assert list(pf_dynamo.generate_post_ids_by_user(user_id)) == ['pid']

    # add another flag by this user, test
    transacts = [pf_dynamo.transact_add('pid2', user_id)]
    pf_dynamo.client.transact_write_items(transacts)
    assert list(pf_dynamo.generate_post_ids_by_user(user_id)) == ['pid', 'pid2']
