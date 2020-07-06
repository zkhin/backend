import uuid

import pendulum
import pytest

from app.mixins.flag.dynamo import FlagDynamo
from app.mixins.flag.exceptions import AlreadyFlagged, NotFlagged


@pytest.fixture
def flag_dynamo(dynamo_client):
    yield FlagDynamo('itype', dynamo_client)


def test_add(flag_dynamo):
    item_id, user_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = pendulum.now('utc')

    # check no flags
    assert flag_dynamo.get(item_id, user_id) is None

    # flag the item, verify
    flag_item = flag_dynamo.add(item_id, user_id, now=now)
    assert flag_dynamo.get(item_id, user_id) == flag_item
    assert flag_item == {
        'schemaVersion': 0,
        'partitionKey': f'itype/{item_id}',
        'sortKey': f'flag/{user_id}',
        'gsiK1PartitionKey': f'flag/{user_id}',
        'gsiK1SortKey': 'itype',
        'createdAt': now.to_iso8601_string(),
    }

    # check we can't re-add same flag item
    with pytest.raises(AlreadyFlagged):
        flag_dynamo.add(item_id, user_id, now=now)

    # check we can flag without specifying the timestamp
    item_id, user_id = str(uuid.uuid4()), str(uuid.uuid4())
    before = pendulum.now('utc')
    flag_item = flag_dynamo.add(item_id, user_id)
    after = pendulum.now('utc')

    assert flag_dynamo.get(item_id, user_id) == flag_item
    created_at = pendulum.parse(flag_item['createdAt'])
    assert created_at >= before
    assert created_at <= after


def test_delete(flag_dynamo):
    item_id, user_id = str(uuid.uuid4()), str(uuid.uuid4())

    # flag a item, verify it's really there
    flag_dynamo.add(item_id, user_id)
    assert flag_dynamo.get(item_id, user_id)

    # delete the flag, verify it's really gone
    flag_dynamo.delete(item_id, user_id)
    assert flag_dynamo.get(item_id, user_id) is None

    # verify we can't delete a flag that isn't there
    with pytest.raises(NotFlagged):
        flag_dynamo.delete(item_id, user_id)


def test_delete_all_for_item(flag_dynamo):
    item_id_1, item_id_2 = str(uuid.uuid4()), str(uuid.uuid4())
    assert list(flag_dynamo.generate_by_item(item_id_1)) == []
    assert list(flag_dynamo.generate_by_item(item_id_2)) == []

    # add a flag to item 2 as a distraction, should not be touched
    flag_dynamo.add(item_id_2, 'uid')
    dummy = next(flag_dynamo.generate_by_item(item_id_2))

    # test deleting none
    flag_dynamo.delete_all_for_item(item_id_1)
    assert list(flag_dynamo.generate_by_item(item_id_1)) == []
    assert list(flag_dynamo.generate_by_item(item_id_2)) == [dummy]

    # add two flags to the item
    flag_dynamo.add(item_id_1, 'uid')
    flag_dynamo.add(item_id_1, 'uid2')
    assert len(list(flag_dynamo.generate_by_item(item_id_1))) == 2

    # test deleting those two
    flag_dynamo.delete_all_for_item(item_id_1)
    assert list(flag_dynamo.generate_by_item(item_id_1)) == []
    assert list(flag_dynamo.generate_by_item(item_id_2)) == [dummy]


def test_generate_by_item(flag_dynamo):
    item_id = str(uuid.uuid4())

    # add a flag for a different item
    flag_dynamo.add('id-other', 'uid')

    # test generate no items
    assert list(flag_dynamo.generate_by_item(item_id)) == []
    assert list(flag_dynamo.generate_by_item(item_id)) == []

    # add a flag for this item
    flag_dynamo.add(item_id, 'uid')

    # test generate one item
    items = list(flag_dynamo.generate_by_item(item_id))
    assert len(items) == 1
    assert items[0]['partitionKey'] == f'itype/{item_id}'
    assert items[0]['sortKey'] == 'flag/uid'

    # add another flag for this item
    flag_dynamo.add(item_id, 'uid2')

    # test generate two items
    items = list(flag_dynamo.generate_by_item(item_id))
    assert len(items) == 2
    assert items[0]['partitionKey'] == f'itype/{item_id}'
    assert items[0]['sortKey'] == 'flag/uid'
    assert items[1]['partitionKey'] == f'itype/{item_id}'
    assert items[1]['sortKey'] == 'flag/uid2'

    # check the pks_only flag works
    items = list(flag_dynamo.generate_by_item(item_id, pks_only=True))
    assert len(items) == 2
    assert items[0] == {'partitionKey': f'itype/{item_id}', 'sortKey': 'flag/uid'}
    assert items[1] == {'partitionKey': f'itype/{item_id}', 'sortKey': 'flag/uid2'}


def test_generate_item_ids_by_user(flag_dynamo):
    user_id = str(uuid.uuid4())

    # add a flag by a different user, test
    flag_dynamo.add('iid', 'uid-other')
    assert list(flag_dynamo.generate_item_ids_by_user(user_id)) == []

    # add a flag by this user, test
    flag_dynamo.add('iid', user_id)
    assert list(flag_dynamo.generate_item_ids_by_user(user_id)) == ['iid']

    # add another flag by this user, test
    flag_dynamo.add('iid2', user_id)
    assert list(flag_dynamo.generate_item_ids_by_user(user_id)) == ['iid', 'iid2']
