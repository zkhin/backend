import logging
from decimal import Decimal
from unittest.mock import Mock, call
from uuid import uuid4

import pendulum
import pytest


@pytest.mark.parametrize('manager', pytest.lazy_fixture(['user_manager', 'post_manager']))
def test_trending_deflate(manager):
    key_attributes = ['partitionKey', 'sortKey', 'gsiK3PartitionKey', 'gsiK3SortKey']

    # test with none
    manager.trending_deflate_item = Mock()
    resp = manager.trending_deflate()
    assert resp == (0, 0)
    assert manager.trending_deflate_item.mock_calls == []

    # test with one
    manager.trending_deflate_item = Mock(return_value=True)
    item1 = manager.trending_dynamo.add(str(uuid4()), Decimal(2))
    keys1 = {k: item1[k] for k in key_attributes}
    now = pendulum.now('utc')
    resp = manager.trending_deflate(now=now)
    assert resp == (1, 1)
    assert manager.trending_deflate_item.mock_calls == [call(keys1, now=now)]

    # test with two, order
    manager.trending_deflate_item = Mock(return_value=False)
    item2 = manager.trending_dynamo.add(str(uuid4()), Decimal(3))
    keys2 = {k: item2[k] for k in key_attributes}
    now = pendulum.now('utc')
    resp = manager.trending_deflate(now=now)
    assert resp == (2, 0)
    assert manager.trending_deflate_item.mock_calls == [call(keys1, now=now), call(keys2, now=now)]

    # test with three, order
    manager.trending_deflate_item = Mock(return_value=True)
    item3 = manager.trending_dynamo.add(str(uuid4()), Decimal(2.5))
    keys3 = {k: item3[k] for k in key_attributes}
    now = pendulum.now('utc')
    resp = manager.trending_deflate(now=now)
    assert resp == (3, 3)
    assert manager.trending_deflate_item.mock_calls == [
        call(keys1, now=now),
        call(keys3, now=now),
        call(keys2, now=now),
    ]


@pytest.mark.parametrize('manager', pytest.lazy_fixture(['user_manager', 'post_manager']))
def test_trending_deflate_item_retry_count(manager):
    # add a trending item
    item_id, item_score = str(uuid4()), Decimal(0.4)
    item = manager.trending_dynamo.add(item_id, item_score, now=pendulum.now('utc').subtract(days=1))

    with pytest.raises(Exception, match=f'failed for item `{manager.item_type}:{item_id}` after 3 tries'):
        manager.trending_deflate_item(item, retry_count=3)
    manager.trending_deflate_item(item, retry_count=2)  # no exception thrown


@pytest.mark.parametrize('manager', pytest.lazy_fixture(['user_manager', 'post_manager']))
def test_trending_deflate_item_already_deflated_today(manager, caplog):
    # add a trending item
    item_id, item_score = str(uuid4()), Decimal(0.4)
    item = manager.trending_dynamo.add(item_id, item_score)
    manager.trending_dynamo.deflate_score = Mock()

    with caplog.at_level(logging.WARNING):
        deflated = manager.trending_deflate_item(item)
    assert deflated is False
    assert len(caplog.records) == 1
    assert manager.item_type in caplog.records[0].msg
    assert item_id in caplog.records[0].msg
    assert 'already been deflated today' in caplog.records[0].msg
    assert manager.trending_dynamo.deflate_score.mock_calls == []


@pytest.mark.parametrize('manager', pytest.lazy_fixture(['user_manager', 'post_manager']))
def test_trending_deflate_item_already_has_score_of_zero(manager, caplog):
    # add a trending item
    item_id, item_score = str(uuid4()), Decimal(0)
    item = manager.trending_dynamo.add(item_id, item_score)
    manager.trending_dynamo.deflate_score = Mock()

    with caplog.at_level(logging.WARNING):
        deflated = manager.trending_deflate_item(item)
    assert deflated is False
    assert len(caplog.records) == 1
    assert manager.item_type in caplog.records[0].msg
    assert item_id in caplog.records[0].msg
    assert 'already has score of zero' in caplog.records[0].msg
    assert manager.trending_dynamo.deflate_score.mock_calls == []


@pytest.mark.parametrize('manager', pytest.lazy_fixture(['user_manager', 'post_manager']))
def test_trending_deflate_item_no_recursion_without_last_deflated_at_assumption(manager, caplog):
    # add a trending item
    created_at = pendulum.parse('2020-06-07T12:00:00Z')
    item_id, item_score = str(uuid4()), Decimal(0.4)
    item = manager.trending_dynamo.add(item_id, item_score, now=created_at)
    assert pendulum.parse(item['lastDeflatedAt']) == created_at
    assert item['gsiK3SortKey'] == pytest.approx(Decimal(0.4))

    # do the deflation, next day
    now = pendulum.parse('2020-06-08T18:00:00Z')
    with caplog.at_level(logging.WARNING):
        deflated = manager.trending_deflate_item(item, now=now)
    assert deflated is True
    assert caplog.records == []
    item = manager.trending_dynamo.get(item_id)
    assert pendulum.parse(item['lastDeflatedAt']) == now
    assert item['gsiK3SortKey'] == pytest.approx(Decimal(0.20))


@pytest.mark.parametrize('manager', pytest.lazy_fixture(['user_manager', 'post_manager']))
def test_trending_deflate_item_no_recursion_with_last_deflated_at_assumption(manager, caplog):
    # add a trending item
    created_at = pendulum.parse('2020-06-07T12:00:00Z')
    item_id, item_score = str(uuid4()), Decimal(0.4)
    item = manager.trending_dynamo.add(item_id, item_score, now=created_at)
    assert pendulum.parse(item['lastDeflatedAt']) == created_at
    assert item['gsiK3SortKey'] == pytest.approx(Decimal(0.4))
    keys = {
        k: v for k, v in item.items() if k in ('partitionKey', 'sortKey', 'gsiK3PartitionKey', 'gsiK3SortKey')
    }

    # do the deflation, next day, so the common case assumption (that the job is run once per day) should hold
    now = pendulum.parse('2020-06-08T18:00:00Z')
    with caplog.at_level(logging.WARNING):
        deflated = manager.trending_deflate_item(keys, now=now)
    assert deflated is True
    assert caplog.records == []
    item = manager.trending_dynamo.get(item_id)
    assert pendulum.parse(item['lastDeflatedAt']) == now
    assert item['gsiK3SortKey'] == pytest.approx(Decimal(0.20))


@pytest.mark.parametrize('manager', pytest.lazy_fixture(['user_manager', 'post_manager']))
def test_trending_deflate_item_with_recursion_with_last_deflated_at_assumption(manager, caplog):
    # add a trending item
    created_at = pendulum.parse('2020-06-07T12:00:00Z')
    item_id, item_score = str(uuid4()), Decimal(0.4)
    item = manager.trending_dynamo.add(item_id, item_score, now=created_at)
    assert pendulum.parse(item['lastDeflatedAt']) == created_at
    assert item['gsiK3SortKey'] == pytest.approx(Decimal(0.4))
    keys = {
        k: v for k, v in item.items() if k in ('partitionKey', 'sortKey', 'gsiK3PartitionKey', 'gsiK3SortKey')
    }

    # do a deflation run two days later, so the common case asumption fails
    now = pendulum.parse('2020-06-09T18:00:00Z')
    with caplog.at_level(logging.WARNING):
        deflated = manager.trending_deflate_item(keys, now=now)
    assert deflated is True
    assert len(caplog.records) == 1
    assert 'trying again' in caplog.records[0].msg
    assert manager.item_type in caplog.records[0].msg
    assert item_id in caplog.records[0].msg

    # verify it was deflated correctly
    item = manager.trending_dynamo.get(item_id)
    assert pendulum.parse(item['lastDeflatedAt']) == now
    assert item['gsiK3SortKey'] == pytest.approx(Decimal(0.10))  # two days worth of deflating


@pytest.mark.parametrize('manager', pytest.lazy_fixture(['user_manager', 'post_manager']))
def test_trending_deflate_item_with_recursion_without_last_deflated_at_assumption(manager, caplog):
    # add a trending item
    created_at = pendulum.parse('2020-06-07T12:00:00Z')
    item_id, item_score = str(uuid4()), Decimal(0.4)
    item = manager.trending_dynamo.add(item_id, item_score, now=created_at)
    assert pendulum.parse(item['lastDeflatedAt']) == created_at
    assert item['gsiK3SortKey'] == pytest.approx(Decimal(0.4))

    # sneak behind our manager's back and increment its score
    manager.trending_dynamo.add_score(item_id, Decimal(1), created_at)

    # do a deflation run
    now = pendulum.parse('2020-06-08T18:00:00Z')
    with caplog.at_level(logging.WARNING):
        deflated = manager.trending_deflate_item(item, now=now)
    assert deflated is True
    assert len(caplog.records) == 1
    assert 'trying again' in caplog.records[0].msg
    assert manager.item_type in caplog.records[0].msg
    assert item_id in caplog.records[0].msg

    # verify it was deflated correctly
    item = manager.trending_dynamo.get(item_id)
    assert pendulum.parse(item['lastDeflatedAt']) == now
    assert item['gsiK3SortKey'] == pytest.approx(Decimal(0.7))


@pytest.mark.parametrize('manager', pytest.lazy_fixture(['user_manager', 'post_manager']))
def test_trending_delete_tail(manager):
    assert manager.min_count_to_keep == 10 * 1000
    assert manager.min_score_to_keep == 0.5
    manager.trending_dynamo.delete = Mock(wraps=manager.trending_dynamo.delete)

    # test none to delete
    cnt = manager.trending_delete_tail(10000)
    assert cnt == 0
    assert manager.trending_dynamo.delete.mock_calls == []

    # test one to delete
    manager.trending_dynamo.delete.reset_mock()
    item1_id, item1_score = str(uuid4()), Decimal(0.25)
    manager.trending_dynamo.add(item1_id, item1_score)
    cnt = manager.trending_delete_tail(10001)
    assert cnt == 1
    assert manager.trending_dynamo.delete.mock_calls == [call(item1_id, expected_score=item1_score)]
    assert manager.trending_dynamo.get(item1_id) is None

    # test two to delete, one spared by count
    manager.trending_dynamo.delete.reset_mock()
    item1_id, item1_score = str(uuid4()), Decimal(0.33)
    item2_id, item2_score = str(uuid4()), Decimal(0.25)
    item3_id, item3_score = str(uuid4()), Decimal(0.4)
    manager.trending_dynamo.add(item1_id, item1_score)
    manager.trending_dynamo.add(item2_id, item2_score)
    manager.trending_dynamo.add(item3_id, item3_score)
    cnt = manager.trending_delete_tail(10002)
    assert cnt == 2
    assert manager.trending_dynamo.delete.mock_calls == [
        call(item2_id, expected_score=item2_score),
        call(item1_id, expected_score=pytest.approx(item1_score)),
    ]
    assert manager.trending_dynamo.get(item1_id) is None
    assert manager.trending_dynamo.get(item2_id) is None
    assert manager.trending_dynamo.get(item3_id)
    manager.trending_dynamo.delete(item3_id)

    # test three to delete, two spared by score
    manager.trending_dynamo.delete.reset_mock()
    item1_id, item1_score = str(uuid4()), Decimal(0.50)
    item2_id, item2_score = str(uuid4()), Decimal(0.25)
    item3_id, item3_score = str(uuid4()), Decimal(0.55)
    manager.trending_dynamo.add(item1_id, item1_score)
    manager.trending_dynamo.add(item2_id, item2_score)
    manager.trending_dynamo.add(item3_id, item3_score)
    cnt = manager.trending_delete_tail(10003)
    assert cnt == 1
    assert manager.trending_dynamo.delete.mock_calls == [
        call(item2_id, expected_score=item2_score),
    ]
    assert manager.trending_dynamo.get(item1_id)
    assert manager.trending_dynamo.get(item2_id) is None
    assert manager.trending_dynamo.get(item3_id)


@pytest.mark.parametrize('manager', pytest.lazy_fixture(['user_manager', 'post_manager']))
def test_trending_delete_tail_race_condition(manager, caplog):
    assert manager.min_count_to_keep == 10 * 1000
    assert manager.min_score_to_keep == 0.5
    manager.trending_dynamo.delete = Mock(wraps=manager.trending_dynamo.delete)

    # set up two to delete
    manager.trending_dynamo.delete.reset_mock()
    item1_id, item1_score = str(uuid4()), Decimal(0.33)
    item2_id, item2_score, item2_lda = str(uuid4()), Decimal(0.25), pendulum.now('utc')
    manager.trending_dynamo.add(item1_id, item1_score)
    manager.trending_dynamo.add(item2_id, item2_score, now=item2_lda)

    # mock the generator so we can make a race condition
    keys = list(manager.trending_dynamo.generate_keys())
    manager.trending_dynamo.generate_keys = Mock(return_value=(k for k in keys))

    # add more score to one of them to create the rce condition
    manager.trending_dynamo.add_score(item2_id, Decimal(1), item2_lda)

    # do the tail delete
    with caplog.at_level(logging.WARNING):
        cnt = manager.trending_delete_tail(10002)
    assert cnt == 1
    assert len(caplog.records) == 1
    assert 'not deleting trending' in caplog.records[0].msg
    assert item2_id in caplog.records[0].msg

    assert manager.trending_dynamo.delete.mock_calls == [
        call(item2_id, expected_score=pytest.approx(item2_score)),  # calls, but fails
        call(item1_id, expected_score=pytest.approx(item1_score)),
    ]
    assert manager.trending_dynamo.get(item1_id) is None
    assert manager.trending_dynamo.get(item2_id)
