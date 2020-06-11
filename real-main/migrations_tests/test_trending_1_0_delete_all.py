import logging
from decimal import Decimal
from uuid import uuid4

import pendulum
import pytest

from migrations.trending_1_0_delete_all import Migration


@pytest.fixture
def new_trending(dynamo_table):
    "To use as a distraction, shouldn't be touched"
    post_id = str(uuid4())
    now_str = pendulum.now('utc').to_iso8601_string()
    item = {
        'partitionKey': f'post/{post_id}',
        'sortKey': 'trending',
        'schemaVersion': 0,
        'gsiK3PartitionKey': 'post/trending',
        'gsiK3SortKey': Decimal(2),
        'lastDeflatedAt': now_str,
        'createdAt': now_str,
    }
    dynamo_table.put_item(Item=item)
    yield item


@pytest.fixture
def user_trending(dynamo_table):
    item_id = str(uuid4())
    item = {
        'partitionKey': f'trending/{item_id}',
        'sortKey': '-',
        'schemaVersion': 0,
        'pendingViewCount': 42,
        'gsiA1PartitionKey': 'trending/user',
        'gsiA1SortKey': pendulum.now('utc').to_iso8601_string(),
        'gsiK3PartitionKey': 'trending/user',
        'gsiK3SortKey': Decimal(1 / 6).normalize(),
    }
    dynamo_table.put_item(Item=item)
    yield item


@pytest.fixture
def post_trending(dynamo_table):
    item_id = str(uuid4())
    item = {
        'partitionKey': f'trending/{item_id}',
        'sortKey': '-',
        'schemaVersion': 0,
        'pendingViewCount': 42,
        'gsiA1PartitionKey': 'trending/post',
        'gsiA1SortKey': pendulum.now('utc').to_iso8601_string(),
        'gsiK3PartitionKey': 'trending/post',
        'gsiK3SortKey': Decimal(7 / 4).normalize(),
    }
    dynamo_table.put_item(Item=item)
    yield item


def test_nothing_to_migrate(dynamo_client, dynamo_table, caplog, new_trending):
    # verify starting state
    pk = {'partitionKey': new_trending['partitionKey'], 'sortKey': new_trending['sortKey']}
    assert dynamo_table.get_item(Key=pk)['Item'] == new_trending

    # do the migration
    migration = Migration(dynamo_client, dynamo_table)
    with caplog.at_level(logging.WARNING):
        migration.run()
    assert len(caplog.records) == 0

    # verify no change in db
    assert dynamo_table.get_item(Key=pk)['Item'] == new_trending


@pytest.mark.parametrize('trending', pytest.lazy_fixture(['user_trending', 'post_trending']))
def test_migrate_one(dynamo_client, dynamo_table, caplog, trending):
    # verify starting state
    item_pk = trending['partitionKey']
    item_key = {'partitionKey': item_pk, 'sortKey': '-'}
    assert dynamo_table.get_item(Key=item_key)['Item'] == trending

    # do the migration
    migration = Migration(dynamo_client, dynamo_table)
    with caplog.at_level(logging.WARNING):
        migration.run()
    assert len(caplog.records) == 1
    assert 'Deleting' in str(caplog.records[0])
    assert item_pk in str(caplog.records[0])

    # verify final state
    assert 'Item' not in dynamo_table.get_item(Key=item_key)


def test_migrate_multiple(dynamo_client, dynamo_table, caplog, user_trending, post_trending):
    # verify starting state
    user_pk = user_trending['partitionKey']
    post_pk = post_trending['partitionKey']
    user_key = {'partitionKey': user_pk, 'sortKey': '-'}
    post_key = {'partitionKey': post_pk, 'sortKey': '-'}
    assert dynamo_table.get_item(Key=user_key)['Item'] == user_trending
    assert dynamo_table.get_item(Key=post_key)['Item'] == post_trending

    # do the migration
    migration = Migration(dynamo_client, dynamo_table)
    with caplog.at_level(logging.WARNING):
        migration.run()
    assert len(caplog.records) == 2
    assert all('Deleting' in rec.msg for rec in caplog.records)
    assert sum(user_pk in rec.msg for rec in caplog.records) == 1
    assert sum(post_pk in rec.msg for rec in caplog.records) == 1

    # verify final state
    assert 'Item' not in dynamo_table.get_item(Key=user_key)
    assert 'Item' not in dynamo_table.get_item(Key=post_key)
