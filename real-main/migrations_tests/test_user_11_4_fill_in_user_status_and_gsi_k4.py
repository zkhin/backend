import logging
from uuid import uuid4

import pytest

from migrations.user_11_4_fill_in_user_status_and_gsi_k4 import Migration


@pytest.fixture
def active_user(dynamo_table):
    user_id = f'us-east-1:{uuid4()}'
    item = {'partitionKey': f'user/{user_id}', 'sortKey': 'profile', 'userId': user_id}
    dynamo_table.put_item(Item=item)
    yield item


@pytest.fixture
def anonymous_user(dynamo_table):
    user_id = f'us-east-1:{uuid4()}'
    item = {'partitionKey': f'user/{user_id}', 'sortKey': 'profile', 'userId': user_id, 'userStatus': 'ANONYMOUS'}
    dynamo_table.put_item(Item=item)
    yield item


@pytest.fixture
def disabled_user(dynamo_table):
    user_id = f'us-east-1:{uuid4()}'
    item = {'partitionKey': f'user/{user_id}', 'sortKey': 'profile', 'userId': user_id, 'userStatus': 'DISABLED'}
    dynamo_table.put_item(Item=item)
    yield item


@pytest.fixture
def migrated_user(dynamo_table):
    user_id = f'us-east-1:{uuid4()}'
    item = {
        'partitionKey': f'user/{user_id}',
        'sortKey': 'profile',
        'userId': user_id,
        'userStatus': 'ACTIVE',
        'gsiK4PartitionKey': 'user',
        'gsiK4SortKey': 'ACTIVE',
    }
    dynamo_table.put_item(Item=item)
    yield item


def test_nothing_to_migrate(dynamo_client, dynamo_table, caplog, migrated_user):
    key = {k: migrated_user[k] for k in ('partitionKey', 'sortKey')}
    assert 'userStatus' in migrated_user
    assert 'gsiK4PartitionKey' in migrated_user
    assert 'gsiK4SortKey' in migrated_user
    assert dynamo_table.get_item(Key=key)['Item'] == migrated_user

    # do the migration, check user0 unchanged
    migration = Migration(dynamo_client, dynamo_table)
    with caplog.at_level(logging.WARNING):
        migration.run()
    assert len(caplog.records) == 0
    assert dynamo_table.get_item(Key=key)['Item'] == migrated_user


@pytest.mark.parametrize('user', pytest.lazy_fixture(['active_user', 'anonymous_user', 'disabled_user']))
def test_migrate_one_user(dynamo_client, dynamo_table, caplog, user):
    key = {k: user[k] for k in ('partitionKey', 'sortKey')}
    assert user.get('userStatus') != 'ACTIVE'
    assert 'gsiK4PartitionKey' not in user
    assert 'gsiK4SortKey' not in user
    assert dynamo_table.get_item(Key=key)['Item'] == user

    # do the migration, check logging
    migration = Migration(dynamo_client, dynamo_table)
    with caplog.at_level(logging.WARNING):
        migration.run()
    assert len(caplog.records) == 1
    assert all('Migrating' in rec.msg for rec in caplog.records)
    assert sum(user['userId'] in rec.msg for rec in caplog.records) == 1

    # check final state
    new_user = dynamo_table.get_item(Key=key)['Item']
    assert new_user.pop('gsiK4PartitionKey') == 'user'
    assert new_user.pop('gsiK4SortKey') == new_user['userStatus']
    assert new_user == {'userStatus': 'ACTIVE', **user}


def test_migrate_multiple_users(dynamo_client, dynamo_table, caplog, active_user, anonymous_user, disabled_user):
    users = [active_user, anonymous_user, disabled_user]
    keys = [{k: user[k] for k in ('partitionKey', 'sortKey')} for user in users]
    for key, user in zip(keys, users):
        assert user.get('userStatus') != 'ACTIVE'
        assert 'gsiK4PartitionKey' not in user
        assert 'gsiK4SortKey' not in user
        assert dynamo_table.get_item(Key=key)['Item'] == user

    # do the migration, check logging
    migration = Migration(dynamo_client, dynamo_table)
    with caplog.at_level(logging.WARNING):
        migration.run()
    assert len(caplog.records) == 3
    assert all('Migrating' in rec.msg for rec in caplog.records)
    assert sum(users[0]['userId'] in rec.msg for rec in caplog.records) == 1
    assert sum(users[1]['userId'] in rec.msg for rec in caplog.records) == 1
    assert sum(users[2]['userId'] in rec.msg for rec in caplog.records) == 1

    # check final state
    for key, user in zip(keys, users):
        new_user = dynamo_table.get_item(Key=key)['Item']
        assert new_user.pop('gsiK4PartitionKey') == 'user'
        assert new_user.pop('gsiK4SortKey') == new_user['userStatus']
        assert new_user['userStatus'] == user.get('userStatus', 'ACTIVE')
        assert new_user == {'userStatus': 'ACTIVE', **user}
