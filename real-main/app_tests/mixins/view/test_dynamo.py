from random import randint
from uuid import uuid4

import pendulum
import pytest

from app.mixins.view.dynamo import ViewDynamo
from app.mixins.view.enums import ViewType
from app.mixins.view.exceptions import ViewAlreadyExists, ViewDoesNotExist


@pytest.fixture
def view_dynamo(dynamo_client):
    yield ViewDynamo('itype', dynamo_client)


@pytest.fixture
def item_id():
    return str(uuid4())


@pytest.fixture
def user_id():
    return str(uuid4())


@pytest.fixture
def view_count():
    return randint(1, 10)


@pytest.fixture
def viewed_at():
    return pendulum.now('utc')


view_count1 = view_count
view_count2 = view_count
viewed_at1 = viewed_at
viewed_at2 = viewed_at


@pytest.mark.parametrize('view_type', [None, ViewType.FOCUS, ViewType.THUMBNAIL])
def test_add_view(view_dynamo, item_id, user_id, view_count, viewed_at, view_type):
    viewed_at_str = viewed_at.to_iso8601_string()
    expected_view = {
        'partitionKey': f'itype/{item_id}',
        'sortKey': f'view/{user_id}',
        'schemaVersion': 0,
        'gsiA1PartitionKey': f'itypeView/{item_id}',
        'gsiA1SortKey': viewed_at_str,
        'gsiA2PartitionKey': f'itypeView/{user_id}',
        'gsiA2SortKey': viewed_at_str,
        'viewCount': view_count,
        'firstViewedAt': viewed_at_str,
        'lastViewedAt': viewed_at_str,
    }
    if view_type == ViewType.FOCUS:
        expected_view['focusViewCount'] = view_count
        expected_view['focusLastViewedAt'] = viewed_at_str
    if view_type == ViewType.THUMBNAIL:
        expected_view['thumbnailViewCount'] = view_count
        expected_view['thumbnailLastViewedAt'] = viewed_at_str
    assert view_dynamo.add_view(item_id, user_id, view_count, viewed_at, view_type=view_type) == expected_view
    assert view_dynamo.get_view(item_id, user_id) == expected_view


def test_add_view_cant_ad_view_that_already_exists(view_dynamo, item_id, user_id, view_count, viewed_at):
    assert view_dynamo.add_view(item_id, user_id, view_count, viewed_at)
    with pytest.raises(ViewAlreadyExists):
        view_dynamo.add_view(item_id, user_id, randint(1, 10), pendulum.now('utc'))


def test_increment_view_count_error_dne(view_dynamo, item_id, user_id, view_count, viewed_at):
    with pytest.raises(ViewDoesNotExist):
        view_dynamo.increment_view_count(item_id, user_id, view_count, viewed_at)


@pytest.mark.parametrize('view_type1', [None, ViewType.FOCUS, ViewType.THUMBNAIL])
@pytest.mark.parametrize('view_type2', [None, ViewType.FOCUS, ViewType.THUMBNAIL])
def test_increment_view_count(
    view_dynamo, item_id, user_id, view_count1, view_count2, viewed_at1, viewed_at2, view_type1, view_type2
):
    org_view = view_dynamo.add_view(item_id, user_id, view_count1, viewed_at1, view_type=view_type1)
    viewed_at2_str = viewed_at2.to_iso8601_string()
    expected_view = {
        **org_view,
        'viewCount': view_count1 + view_count2,
        'lastViewedAt': viewed_at2_str,
    }
    if view_type2 == ViewType.FOCUS:
        expected_view['focusViewCount'] = org_view.get('focusViewCount', 0) + view_count2
        expected_view['focusLastViewedAt'] = viewed_at2_str
    if view_type2 == ViewType.THUMBNAIL:
        expected_view['thumbnailViewCount'] = org_view.get('thumbnailViewCount', 0) + view_count2
        expected_view['thumbnailLastViewedAt'] = viewed_at2_str
    assert (
        view_dynamo.increment_view_count(item_id, user_id, view_count2, viewed_at2, view_type=view_type2)
        == expected_view
    )
    assert view_dynamo.get_view(item_id, user_id) == expected_view


def test_generate_keys_by_item_and_generate_keys_by_user(view_dynamo):
    item_id_1, item_id_2 = str(uuid4()), str(uuid4())
    user_id_1, user_id_2 = str(uuid4()), str(uuid4())

    # user1 views both items, user2 views just item2
    view_dynamo.add_view(item_id_1, user_id_1, 1, pendulum.now('utc'))
    view_dynamo.add_view(item_id_2, user_id_1, 1, pendulum.now('utc'))
    view_dynamo.add_view(item_id_2, user_id_2, 1, pendulum.now('utc'))
    vk11 = view_dynamo.key(item_id_1, user_id_1)
    vk12 = view_dynamo.key(item_id_2, user_id_1)
    vk22 = view_dynamo.key(item_id_2, user_id_2)

    # verify generation by item
    assert list(view_dynamo.generate_keys_by_item(str(uuid4()))) == []
    assert list(view_dynamo.generate_keys_by_item(item_id_1)) == [vk11]
    assert list(view_dynamo.generate_keys_by_item(item_id_2)) == sorted([vk22, vk12], key=lambda x: x['sortKey'])

    # verify generation by user
    assert list(view_dynamo.generate_keys_by_user(str(uuid4()))) == []
    assert list(view_dynamo.generate_keys_by_user(user_id_1)) == [vk11, vk12]
    assert list(view_dynamo.generate_keys_by_user(user_id_2)) == [vk22]


def test_delete_view(view_dynamo):
    # add two views, verify
    item_id1, user_id1 = [str(uuid4()), str(uuid4())]
    item_id2, user_id2 = [str(uuid4()), str(uuid4())]
    view_dynamo.add_view(item_id1, user_id1, 1, pendulum.now('utc'))
    view_dynamo.add_view(item_id2, user_id2, 2, pendulum.now('utc'))
    assert view_dynamo.get_view(item_id1, user_id1)
    assert view_dynamo.get_view(item_id2, user_id2)

    # delete one of the views, verify final state
    resp = view_dynamo.delete_view(item_id1, user_id1)
    assert resp
    assert view_dynamo.get_view(item_id1, user_id1) is None
    assert view_dynamo.get_view(item_id2, user_id2)

    # delete a view that doesn't exist, should fail softly
    resp = view_dynamo.delete_view(item_id1, user_id1)
    assert resp is None


def test_generate_keys_by_user_past_30_days(view_dynamo):
    item_id1, user_id1 = [str(uuid4()), str(uuid4())]
    item_id2, user_id2 = [str(uuid4()), str(uuid4())]
    item_id3, item_id4 = [str(uuid4()), str(uuid4())]
    item1 = view_dynamo.add_view(item_id1, user_id1, 1, pendulum.now('utc'))
    item2 = view_dynamo.add_view(item_id2, user_id2, 1, pendulum.now('utc'))
    item3 = view_dynamo.add_view(item_id3, user_id1, 1, pendulum.now('utc') - pendulum.duration(days=31))
    item4 = view_dynamo.add_view(item_id4, user_id1, 1, pendulum.now('utc') - pendulum.duration(days=29))

    key1 = {k: item1[k] for k in ('partitionKey', 'sortKey')}
    key2 = {k: item2[k] for k in ('partitionKey', 'sortKey')}
    key3 = {k: item3[k] for k in ('partitionKey', 'sortKey')}
    key4 = {k: item4[k] for k in ('partitionKey', 'sortKey')}

    assert view_dynamo.get_view(item_id1, user_id1) == item1
    assert view_dynamo.get_view(item_id2, user_id2) == item2
    assert view_dynamo.get_view(item_id3, user_id1) == item3
    assert view_dynamo.get_view(item_id4, user_id1) == item4

    assert list(view_dynamo.generate_keys_by_user_past_30_days(user_id1)) == [key4, key1]
    assert list(view_dynamo.generate_keys_by_user_past_30_days(user_id2)) == [key2]
    assert list(
        view_dynamo.generate_keys_by_user_past_30_days(user_id1, pendulum.now('utc') - pendulum.duration(days=3))
    ) == [key3, key4, key1]
