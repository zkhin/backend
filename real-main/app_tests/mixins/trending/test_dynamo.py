import uuid
from decimal import Decimal

import pendulum
import pytest

from app.mixins.trending.dynamo import TrendingDynamo
from app.mixins.trending.exceptions import TrendingAlreadyExists, TrendingDNEOrAttributeMismatch


@pytest.fixture
def trending_dynamo(dynamo_client):
    yield TrendingDynamo('itype', dynamo_client)


@pytest.fixture
def trending_dynamo_itype2(dynamo_client):
    yield TrendingDynamo('itype2', dynamo_client)


def test_add(trending_dynamo):
    item_id = str(uuid.uuid4())

    # verify floats are not accepted as scores
    with pytest.raises(AssertionError, match='decimal'):
        trending_dynamo.add(item_id, 42.2)

    # add a trending specifying timestamp, integer score
    assert trending_dynamo.get(item_id) is None
    now = pendulum.now('utc')
    initial_score = Decimal(42)
    item = trending_dynamo.add(item_id, initial_score, now=now)
    assert item == trending_dynamo.get(item_id)
    assert item.pop('partitionKey').split('/') == ['itype', item_id]
    assert item.pop('sortKey') == 'trending'
    assert item.pop('schemaVersion') == 0
    assert pendulum.parse(item.pop('lastDeflatedAt')) == now
    assert pendulum.parse(item.pop('createdAt')) == now
    assert item.pop('gsiK3PartitionKey').split('/') == ['itype', 'trending']
    assert item.pop('gsiK3SortKey') == 42
    assert item == {}

    # verify we can't add another trending for the same item
    with pytest.raises(TrendingAlreadyExists, match=f'itype:{item_id}'):
        trending_dynamo.add(item_id, Decimal(99))

    # add another trending without specifying timestamp, float score
    item_id = str(uuid.uuid4())
    assert trending_dynamo.get(item_id) is None
    initial_score = Decimal(1 / 6)
    before = pendulum.now('utc')
    item = trending_dynamo.add(item_id, initial_score)
    after = pendulum.now('utc')
    assert item == trending_dynamo.get(item_id)
    assert item['gsiK3SortKey'] == initial_score.normalize()
    created_at = pendulum.parse(item['createdAt'])
    assert before < created_at < after
    assert pendulum.parse(item['lastDeflatedAt']) == created_at


def test_add_score_failures(trending_dynamo):
    item_id = str(uuid.uuid4())

    # verify can't add negative score
    with pytest.raises(AssertionError, match='greater than 0'):
        trending_dynamo.add_score(item_id, Decimal(-99), pendulum.now('utc'))

    # verify can't add to trending that doesn't exist
    with pytest.raises(TrendingDNEOrAttributeMismatch, match=f'itype:{item_id}'):
        trending_dynamo.add_score(item_id, Decimal(99), pendulum.now('utc'))

    # verify can't add to trending with treding last deflated at mismatch
    trending_dynamo.add(item_id, Decimal(42), now=pendulum.now('utc'))
    with pytest.raises(TrendingDNEOrAttributeMismatch, match=f'itype:{item_id}'):
        trending_dynamo.add_score(item_id, Decimal(99), pendulum.now('utc'))


def test_add_score_success(trending_dynamo):
    # add a trending to db
    item_id = str(uuid.uuid4())
    now = pendulum.now('utc')
    item = trending_dynamo.add(item_id, Decimal(42), now=now)
    assert item['partitionKey'] == f'itype/{item_id}'
    assert item['gsiK3SortKey'] == 42

    # verify we can add an integer to its score
    trending_dynamo.add_score(item_id, Decimal(17), now)
    new_item = trending_dynamo.get(item_id)
    assert new_item['gsiK3SortKey'] == 42 + 17
    item['gsiK3SortKey'] = new_item['gsiK3SortKey']
    assert new_item == item

    # verify we can add a float to its score
    trending_dynamo.add_score(item_id, Decimal(1 / 6), now)
    new_item = trending_dynamo.get(item_id)
    assert new_item['gsiK3SortKey'] == pytest.approx(Decimal(42 + 17 + 1 / 6))
    item['gsiK3SortKey'] = new_item['gsiK3SortKey']
    assert new_item == item


def test_deflate_score_failures(trending_dynamo):
    item_id = str(uuid.uuid4())
    now = pendulum.now('utc')
    yesterday = now.subtract(days=1).date()

    # verify need to use decimals
    with pytest.raises(AssertionError, match='decimal'):
        trending_dynamo.deflate_score(item_id, Decimal(5), 4, yesterday, now)
    with pytest.raises(AssertionError, match='decimal'):
        trending_dynamo.deflate_score(item_id, 5, Decimal(4), yesterday, now)

    # verify can't deflate to less than zero
    with pytest.raises(AssertionError, match='greater than 0'):
        trending_dynamo.deflate_score(item_id, Decimal(5), Decimal(-1), yesterday, now)

    # verify can't deflate to more than our score
    with pytest.raises(AssertionError, match='less than existing'):
        trending_dynamo.deflate_score(item_id, Decimal(5), Decimal(6), yesterday, now)

    # verify can't deflate trending that DNE
    with pytest.raises(TrendingDNEOrAttributeMismatch, match=f'itype:{item_id}'):
        trending_dynamo.deflate_score(item_id, Decimal(5), Decimal(4), yesterday, now)

    # verify can't deflate with expected score mismatch
    trending_dynamo.add(item_id, Decimal(6))
    with pytest.raises(TrendingDNEOrAttributeMismatch, match=f'itype:{item_id}'):
        trending_dynamo.deflate_score(item_id, Decimal(5), Decimal(4), yesterday, now)

    # verify can't deflate with expected deflation date mismatch
    with pytest.raises(TrendingDNEOrAttributeMismatch, match=f'itype:{item_id}'):
        trending_dynamo.deflate_score(item_id, Decimal(6), Decimal(4), yesterday, now)


def test_deflate_score_success(trending_dynamo):
    # add a trending to db
    item_id = str(uuid.uuid4())
    now = pendulum.now('utc')
    item = trending_dynamo.add(item_id, Decimal(6 / 7), now=now)
    assert item['partitionKey'] == f'itype/{item_id}'
    assert pendulum.parse(item['lastDeflatedAt']) == now
    assert item['gsiK3SortKey'] == pytest.approx(Decimal(6 / 7))

    # verify we can deflate score
    now = pendulum.now('utc')
    trending_dynamo.deflate_score(item_id, item['gsiK3SortKey'], Decimal(1 / 6), now.date(), now)
    new_item = trending_dynamo.get(item_id)
    assert pendulum.parse(new_item['lastDeflatedAt']) == now
    assert new_item['gsiK3SortKey'] == pytest.approx(Decimal(1 / 6))
    item['lastDeflatedAt'] = new_item['lastDeflatedAt']
    item['gsiK3SortKey'] = new_item['gsiK3SortKey']
    assert new_item == item


def test_delete_failures(trending_dynamo):
    item_id = str(uuid.uuid4())

    # verify need to use decimals
    with pytest.raises(AssertionError, match='decimal'):
        trending_dynamo.delete(item_id, 5.4)

    # verify can't delete item that DNE if we specify score
    with pytest.raises(TrendingDNEOrAttributeMismatch, match=f'itype:{item_id}'):
        trending_dynamo.delete(item_id, Decimal(5.4))

    # verify can't delete item with score mismatch
    trending_dynamo.add(item_id, Decimal(42))
    with pytest.raises(TrendingDNEOrAttributeMismatch, match=f'itype:{item_id}'):
        trending_dynamo.delete(item_id, Decimal(5.4))


def test_delete_success(trending_dynamo):
    # add an item
    item_id = str(uuid.uuid4())
    item = trending_dynamo.add(item_id, Decimal(1 / 6))
    assert trending_dynamo.get(item_id)

    # delete that item by matching scores, verify it's gone
    deleted_item = trending_dynamo.delete(item_id, Decimal(1 / 6))
    assert deleted_item == item
    assert trending_dynamo.get(item_id) is None

    # add another item
    item_id = str(uuid.uuid4())
    item = trending_dynamo.add(item_id, Decimal(1 / 6))
    assert trending_dynamo.get(item_id)

    # delete that item, verify it's gone
    deleted_item = trending_dynamo.delete(item_id)
    assert deleted_item == item
    assert trending_dynamo.get(item_id) is None

    # verify deletes that don't specify scores are idempotent
    assert trending_dynamo.delete(item_id) is None
    assert trending_dynamo.get(item_id) is None


def test_generate_keys(trending_dynamo, trending_dynamo_itype2):
    item_only_attrs = ('schemaVersion', 'lastDeflatedAt', 'createdAt')

    # add a distraction
    trending_dynamo_itype2.add(str(uuid.uuid4()), Decimal(42))

    # test generate none
    keys = list(trending_dynamo.generate_keys())
    assert len(keys) == 0

    # test generate one
    item1 = trending_dynamo.add(str(uuid.uuid4()), Decimal(42))
    item1_expected_keys = {k: v for k, v in item1.items() if k not in item_only_attrs}
    keys = list(trending_dynamo.generate_keys())
    assert len(keys) == 1
    # TODO: simplify when https://github.com/spulec/moto/issues/3055 addressed
    assert {k: v for k, v in keys[0].items() if k not in item_only_attrs} == item1_expected_keys

    # test generate two, in correct order
    item2 = trending_dynamo.add(str(uuid.uuid4()), Decimal(54))
    item2_expected_keys = {k: v for k, v in item2.items() if k not in item_only_attrs}
    keys = list(trending_dynamo.generate_keys())
    assert len(keys) == 2
    # TODO: simplify when https://github.com/spulec/moto/issues/3055 addressed
    assert {k: v for k, v in keys[0].items() if k not in item_only_attrs} == item1_expected_keys
    assert {k: v for k, v in keys[1].items() if k not in item_only_attrs} == item2_expected_keys

    # test generate three, in correct order
    item3 = trending_dynamo.add(str(uuid.uuid4()), Decimal(40))
    item3_expected_keys = {k: v for k, v in item3.items() if k not in item_only_attrs}
    keys = list(trending_dynamo.generate_keys())
    assert len(keys) == 3
    # TODO: simplify when https://github.com/spulec/moto/issues/3055 addressed
    assert {k: v for k, v in keys[0].items() if k not in item_only_attrs} == item3_expected_keys
    assert {k: v for k, v in keys[1].items() if k not in item_only_attrs} == item1_expected_keys
    assert {k: v for k, v in keys[2].items() if k not in item_only_attrs} == item2_expected_keys
