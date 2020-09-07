import logging
from uuid import uuid4

import pytest

from migrations.post_view_0_4_add_thumbnail_view_count import Migration


@pytest.fixture
def post_view(dynamo_table):
    post_id = str(uuid4())
    user_id = str(uuid4())
    item = {
        'partitionKey': f'post/{post_id}',
        'sortKey': f'view/{user_id}',
        'schemaVersion': 0,
        'viewCount': 2,
        'focusViewCount': 1,
    }
    dynamo_table.put_item(Item=item)
    yield item


pv1 = post_view
pv2 = post_view
pv3 = post_view


def test_nothing_to_migrate(dynamo_client, dynamo_table, caplog):
    # create a distration in the DB
    key = {'partitionKey': f'post/{uuid4()}', 'sortKey': '-'}
    dynamo_table.put_item(Item=key)
    assert dynamo_table.get_item(Key=key)['Item'] == key

    # migrate, check logging
    migration = Migration(dynamo_client, dynamo_table)
    with caplog.at_level(logging.WARNING):
        migration.run()
    assert len(caplog.records) == 0

    # verify final state
    assert dynamo_table.get_item(Key=key)['Item'] == key


def test_migrate_one(dynamo_client, dynamo_table, caplog, post_view):
    # verify starting state
    item = post_view
    post_id = item['partitionKey'].split('/')[1]
    user_id = item['sortKey'].split('/')[1]
    key = {k: item[k] for k in ('partitionKey', 'sortKey')}
    assert dynamo_table.get_item(Key=key)['Item'] == item

    # migrate, check logging
    migration = Migration(dynamo_client, dynamo_table)
    with caplog.at_level(logging.WARNING):
        migration.run()
    assert len(caplog.records) == 1
    assert 'Migrating' in caplog.records[0].msg
    assert post_id in caplog.records[0].msg
    assert user_id in caplog.records[0].msg

    # verify final state
    new_item = dynamo_table.get_item(Key=key)['Item']
    assert new_item.pop('viewCount') == item['viewCount']
    assert new_item.pop('focusViewCount') == item['focusViewCount']
    assert new_item.pop('thumbnailViewCount') == item['viewCount'] - item['focusViewCount']


def test_migrate_multiple(dynamo_client, dynamo_table, caplog, pv1, pv2, pv3):
    items = [pv1, pv2, pv3]

    # verify starting state
    keys = [{k: item[k] for k in ('partitionKey', 'sortKey')} for item in items]
    for key, item in zip(keys, items):
        assert dynamo_table.get_item(Key=key)['Item'] == item

    # migrate, check logging
    migration = Migration(dynamo_client, dynamo_table)
    with caplog.at_level(logging.WARNING):
        migration.run()
    assert len(caplog.records) == 3

    # verify final state
    for key, item in zip(keys, items):
        new_item = dynamo_table.get_item(Key=key)['Item']
        assert new_item.pop('viewCount') == item['viewCount']
        assert new_item.pop('focusViewCount') == item['focusViewCount']
        assert new_item.pop('thumbnailViewCount') == item['viewCount'] - item['focusViewCount']

    # migrate again, test no-op
    caplog.clear()
    migration = Migration(dynamo_client, dynamo_table)
    with caplog.at_level(logging.WARNING):
        migration.run()
    assert len(caplog.records) == 0
