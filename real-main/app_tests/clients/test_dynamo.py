from uuid import uuid4

import pytest
from moto import mock_dynamodb2

from app.clients import DynamoClient


@pytest.fixture
def client():
    partition_key = 'pk'
    sort_key = 'sk'
    with mock_dynamodb2():
        yield DynamoClient(
            table_name='the-table',
            partition_key=partition_key,
            sort_key=sort_key,
            batch_get_items_max=3,
            create_table_schema={
                'KeySchema': [
                    {'AttributeName': partition_key, 'KeyType': 'HASH'},
                    {'AttributeName': sort_key, 'KeyType': 'RANGE'},
                ],
                'AttributeDefinitions': [
                    {'AttributeName': partition_key, 'AttributeType': 'S'},
                    {'AttributeName': sort_key, 'AttributeType': 'S'},
                ],
            },
        )


def test_batch_get_items(client):
    assert client.batch_get_items_max == 3
    assert client.table.scan()['Items'] == []
    pk1, pk2, pk3, pk4 = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
    sk1, sk2, sk3, sk4 = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
    attr1, attr2, attr3, attr4 = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
    all_keys = [{'pk': pk, 'sk': sk} for pk, sk in zip([pk1, pk2, pk3, pk4], [sk1, sk2, sk3, sk4])]

    # add distraction, test get of none
    client.add_item({'Item': {'pk': str(uuid4()), 'sk': str(uuid4())}})
    assert list(client.batch_get_items(iter(all_keys))) == []

    # add one item, test get
    item1 = {'pk': pk1, 'sk': sk1, 'attr': attr1}
    client.add_item({'Item': item1})
    assert list(client.batch_get_items(iter(all_keys))) == [item1]

    # add another item, test get
    item2 = {'pk': pk2, 'sk': sk2, 'attr': attr2}
    client.add_item({'Item': item2})
    items = list(client.batch_get_items(iter(all_keys)))
    assert len(items) == 2
    assert item1 in items
    assert item2 in items

    # add another item, test get
    item3 = {'pk': pk3, 'sk': sk3, 'attr': attr3}
    client.add_item({'Item': item3})
    items = list(client.batch_get_items(iter(all_keys)))
    assert len(items) == 3
    assert item1 in items
    assert item2 in items
    assert item3 in items

    # add another item, test get
    item4 = {'pk': pk4, 'sk': sk4, 'attr': attr4}
    client.add_item({'Item': item4})
    items = list(client.batch_get_items(iter(all_keys)))
    assert len(items) == 4
    assert item1 in items
    assert item2 in items
    assert item3 in items
    assert item4 in items


def test_batch_get_items_projection_expression(client):
    pk, sk, a1, a2, a3 = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
    key = {'pk': pk, 'sk': sk}
    item = {**key, 'a1': a1, 'a2': a2, 'a3': a3}
    client.add_item({'Item': item})
    assert client.table.scan()['Items'] == [item]

    # no projection expression
    assert list(client.batch_get_items(iter([key]))) == [item]

    # with projection expression
    assert list(client.batch_get_items(iter([key]), projection_expression='pk, a1, a3, a5')) == [
        {'pk': pk, 'a1': a1, 'a3': a3}
    ]
