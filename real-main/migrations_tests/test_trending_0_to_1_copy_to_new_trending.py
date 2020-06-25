import logging
from decimal import Decimal
from uuid import uuid4

import pendulum
import pytest

from migrations.trending_0_to_1_copy_to_new_trending import Migration


@pytest.fixture
def trending_already_migrated(dynamo_table):
    item_id = str(uuid4())
    item = {
        'partitionKey': f'trending/{item_id}',
        'sortKey': '-',
        'schemaVersion': 1,
        'pendingViewCount': 42,
        'gsiA1PartitionKey': 'trending/user',
        'gsiA1SortKey': pendulum.now('utc').to_iso8601_string(),
        'gsiK3PartitionKey': 'trending/user',
        'gsiK3SortKey': Decimal(2),
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


def test_migrate_none(dynamo_client, dynamo_table, caplog, trending_already_migrated):
    # check starting state
    item = trending_already_migrated
    pk = {k: item[k] for k in ('partitionKey', 'sortKey')}
    assert dynamo_table.get_item(Key=pk)['Item'] == item

    # migrate, check logging, final state
    migration = Migration(dynamo_client, dynamo_table)
    with caplog.at_level(logging.WARNING):
        migration.run()
    assert len(caplog.records) == 0
    assert dynamo_table.get_item(Key=pk)['Item'] == item


def test_migrate_user_trending(dynamo_client, dynamo_table, caplog, user_trending):
    # check starting state
    assert user_trending['schemaVersion'] == 0
    org_pk = {k: user_trending[k] for k in ('partitionKey', 'sortKey')}
    user_id = user_trending['partitionKey'].split('/')[1]
    new_pk = {'partitionKey': f'user/{user_id}', 'sortKey': 'trending'}
    assert dynamo_table.get_item(Key=org_pk)['Item'] == user_trending
    assert 'Item' not in dynamo_table.get_item(Key=new_pk)

    # migrate, check logging
    migration = Migration(dynamo_client, dynamo_table)
    with caplog.at_level(logging.WARNING):
        before = pendulum.now('utc')
        migration.run()
        after = pendulum.now('utc')
    assert len(caplog.records) == 3
    assert all(user_trending['partitionKey'] in rec.msg for rec in caplog.records)
    assert 'migrating' in caplog.records[0].msg
    assert 'adding new' in caplog.records[1].msg
    assert new_pk['partitionKey'] in caplog.records[1].msg
    assert 'updating schema version' in caplog.records[2].msg

    # check final state
    old_trending = dynamo_table.get_item(Key=org_pk)['Item']
    assert old_trending.pop('schemaVersion') == 1
    assert user_trending.pop('schemaVersion') == 0
    assert old_trending == user_trending

    new_trending = dynamo_table.get_item(Key=new_pk)['Item']
    assert new_trending.pop('partitionKey').split('/') == ['user', user_id]
    assert new_trending.pop('sortKey') == 'trending'
    assert new_trending.pop('schemaVersion') == 0
    assert before < pendulum.parse(new_trending.pop('lastDeflatedAt')) < after
    assert before < pendulum.parse(new_trending.pop('createdAt')) < after
    assert new_trending.pop('gsiK3PartitionKey') == 'user/trending'
    assert new_trending.pop('gsiK3SortKey') == user_trending['gsiK3SortKey']


def test_migrate_post_trending(dynamo_client, dynamo_table, caplog, post_trending):
    # check starting state
    assert post_trending['schemaVersion'] == 0
    org_pk = {k: post_trending[k] for k in ('partitionKey', 'sortKey')}
    post_id = post_trending['partitionKey'].split('/')[1]
    new_pk = {'partitionKey': f'post/{post_id}', 'sortKey': 'trending'}
    assert dynamo_table.get_item(Key=org_pk)['Item'] == post_trending
    assert 'Item' not in dynamo_table.get_item(Key=new_pk)

    # migrate, check logging
    migration = Migration(dynamo_client, dynamo_table)
    with caplog.at_level(logging.WARNING):
        before = pendulum.now('utc')
        migration.run()
        after = pendulum.now('utc')
    assert len(caplog.records) == 3
    assert all(post_trending['partitionKey'] in rec.msg for rec in caplog.records)
    assert 'migrating' in caplog.records[0].msg
    assert 'adding new' in caplog.records[1].msg
    assert new_pk['partitionKey'] in caplog.records[1].msg
    assert 'updating schema version' in caplog.records[2].msg

    # check final state
    old_trending = dynamo_table.get_item(Key=org_pk)['Item']
    assert old_trending.pop('schemaVersion') == 1
    assert post_trending.pop('schemaVersion') == 0
    assert old_trending == post_trending

    new_trending = dynamo_table.get_item(Key=new_pk)['Item']
    assert new_trending.pop('partitionKey').split('/') == ['post', post_id]
    assert new_trending.pop('sortKey') == 'trending'
    assert new_trending.pop('schemaVersion') == 0
    assert before < pendulum.parse(new_trending.pop('lastDeflatedAt')) < after
    assert before < pendulum.parse(new_trending.pop('createdAt')) < after
    assert new_trending.pop('gsiK3PartitionKey') == 'post/trending'
    assert new_trending.pop('gsiK3SortKey') == post_trending['gsiK3SortKey']


def test_race_condition_on_adding_new_trending(dynamo_client, dynamo_table, caplog, user_trending):
    # check starting state
    assert user_trending['schemaVersion'] == 0
    org_pk = {k: user_trending[k] for k in ('partitionKey', 'sortKey')}
    user_id = user_trending['partitionKey'].split('/')[1]
    new_pk = {'partitionKey': f'user/{user_id}', 'sortKey': 'trending'}
    assert dynamo_table.get_item(Key=org_pk)['Item'] == user_trending
    assert 'Item' not in dynamo_table.get_item(Key=new_pk)

    org_score = user_trending['gsiK3SortKey']
    conflict_score = Decimal(4)

    # add an new trending item directly to the DB for this user so we have a race condition
    migration = Migration(dynamo_client, dynamo_table)
    migration.add_new_trending('user', user_id, conflict_score)
    conflict_item = dynamo_table.get_item(Key=new_pk)['Item']
    assert conflict_item['gsiK3SortKey'] == conflict_score

    # run the add, check logging
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        migration.add_new_trending('user', user_id, org_score)
    assert len(caplog.records) == 3
    assert all(user_trending['partitionKey'] in rec.msg for rec in caplog.records)
    assert all(new_pk['partitionKey'] in rec.msg for rec in caplog.records)
    assert 'adding new' in caplog.records[0].msg
    assert 'adding new' in caplog.records[1].msg
    assert 'FAILED' in caplog.records[1].msg
    assert 'updating new' in caplog.records[2].msg

    # check final state
    final_item = dynamo_table.get_item(Key=new_pk)['Item']
    assert final_item.pop('gsiK3SortKey') == pytest.approx(conflict_score + org_score)
    assert conflict_item.pop('gsiK3SortKey') == conflict_score
    assert final_item == conflict_item


def test_migrate_multiple(dynamo_client, dynamo_table, caplog, user_trending, post_trending):
    # check starting state
    org_user_pk = {k: user_trending[k] for k in ('partitionKey', 'sortKey')}
    org_post_pk = {k: post_trending[k] for k in ('partitionKey', 'sortKey')}
    assert dynamo_table.get_item(Key=org_user_pk)['Item'] == user_trending
    assert dynamo_table.get_item(Key=org_post_pk)['Item'] == post_trending

    # migrate, check logging
    migration = Migration(dynamo_client, dynamo_table)
    with caplog.at_level(logging.WARNING):
        migration.run()
    assert len(caplog.records) == 6
    assert sum(1 for rec in caplog.records if user_trending['partitionKey'] in rec.msg) == 3
    assert sum(1 for rec in caplog.records if post_trending['partitionKey'] in rec.msg) == 3

    # check final state
    new_user_trending = dynamo_table.get_item(Key=org_user_pk)['Item']
    new_post_trending = dynamo_table.get_item(Key=org_post_pk)['Item']
    assert new_user_trending.pop('schemaVersion') == 1
    assert new_post_trending.pop('schemaVersion') == 1
    assert user_trending.pop('schemaVersion') == 0
    assert post_trending.pop('schemaVersion') == 0
    assert new_user_trending == user_trending
    assert new_post_trending == post_trending
