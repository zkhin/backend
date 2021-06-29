import logging
from uuid import uuid4

import pendulum
import pytest

from migrations.post_3_3_fill_in_payment_ticker import Migration


@pytest.fixture
def post(dynamo_table):
    post_id = str(uuid4())
    item = {
        'partitionKey': f'post/{post_id}',
        'sortKey': '-',
        'postId': post_id,
        'postedAt': pendulum.now('utc').to_iso8601_string(),
    }
    dynamo_table.put_item(Item=item)
    yield item


post1 = post
post2 = post
post3 = post


@pytest.fixture
def post_with_ticker(dynamo_table):
    post_id = str(uuid4())
    item = {
        'partitionKey': f'post/{post_id}',
        'sortKey': '-',
        'postId': post_id,
        'paymentTicker': 'foo',
    }
    dynamo_table.put_item(Item=item)
    yield item


@pytest.fixture
def ad_post(dynamo_table):
    post_id = str(uuid4())
    item = {
        'partitionKey': f'post/{post_id}',
        'sortKey': '-',
        'postId': post_id,
        'adStatus': str(uuid4()),
    }
    dynamo_table.put_item(Item=item)
    yield item


def test_nothing_to_migrate(dynamo_client, dynamo_table, caplog, post_with_ticker, ad_post):
    post0 = post_with_ticker
    post1 = ad_post
    key0 = {k: post0[k] for k in ('partitionKey', 'sortKey')}
    key1 = {k: post1[k] for k in ('partitionKey', 'sortKey')}
    assert dynamo_table.get_item(Key=key0)['Item'] == post0
    assert dynamo_table.get_item(Key=key1)['Item'] == post1

    # do the migration, check post0 unchanged
    migration = Migration(dynamo_client, dynamo_table)
    with caplog.at_level(logging.WARNING):
        migration.run()
    assert len(caplog.records) == 0
    assert dynamo_table.get_item(Key=key0)['Item'] == post0
    assert dynamo_table.get_item(Key=key1)['Item'] == post1


def test_migrate_one_post(dynamo_client, dynamo_table, caplog, post):
    key = {k: post[k] for k in ('partitionKey', 'sortKey')}
    assert dynamo_table.get_item(Key=key)['Item'] == post
    assert 'paymentTicker' not in post
    assert 'paymentTickerRequiredToView' not in post
    assert 'gsiA5PartitionKey' not in post
    assert 'gsiA5SortKey' not in post

    # do the migration, check logging
    migration = Migration(dynamo_client, dynamo_table)
    with caplog.at_level(logging.WARNING):
        migration.run()
    assert len(caplog.records) == 1
    assert all(x in caplog.records[0].msg for x in ['Migrating', post['postId']])

    # check final state
    new_post = dynamo_table.get_item(Key=key)['Item']
    assert new_post['paymentTicker'] == 'real'
    assert new_post['paymentTickerRequiredToView'] is False
    assert new_post['gsiA5PartitionKey'] == 'postPaymentTicker/real'
    assert new_post['gsiA5SortKey'] == new_post['postedAt']


def test_migrate_multiple(dynamo_client, dynamo_table, caplog, post1, post2, post3):
    posts = [post1, post2, post3]
    keys = [{k: post[k] for k in ('partitionKey', 'sortKey')} for post in posts]
    for key, post in zip(keys, posts):
        assert dynamo_table.get_item(Key=key)['Item'] == post

    # do the migration, check logging
    migration = Migration(dynamo_client, dynamo_table)
    with caplog.at_level(logging.WARNING):
        migration.run()
    assert len(caplog.records) == 3
    for post in posts:
        assert sum(post['postId'] in rec.msg for rec in caplog.records) == 1
    assert sum('Migrating' not in rec.msg for rec in caplog.records) == 0

    # check final state
    for key in keys:
        new_post = dynamo_table.get_item(Key=key)['Item']
        assert new_post['paymentTicker'] == 'real'
        assert new_post['paymentTickerRequiredToView'] is False
        assert new_post['gsiA5PartitionKey'] == 'postPaymentTicker/real'
        assert new_post['gsiA5SortKey'] == new_post['postedAt']

    # check running again is a no-op
    caplog.clear()
    migration = Migration(dynamo_client, dynamo_table)
    with caplog.at_level(logging.WARNING):
        migration.run()
    assert len(caplog.records) == 0
