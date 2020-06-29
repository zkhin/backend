from uuid import uuid4

import pendulum
import pytest

from app.models.card.dynamo import CardDynamo


@pytest.fixture
def card_dynamo(dynamo_client):
    yield CardDynamo(dynamo_client)


def test_transact_add_card_minimal(card_dynamo):
    card_id = 'cid'
    user_id = 'uid'
    title = 'you should know this'
    action = 'https://some-valid-url.com'

    # add the card to the DB
    before = pendulum.now('utc')
    transact = card_dynamo.transact_add_card(card_id, user_id, title, action)
    card_dynamo.client.transact_write_items([transact])
    after = pendulum.now('utc')

    # retrieve the card and verify the format is as we expect
    card_item = card_dynamo.get_card(card_id)
    created_at_str = card_item['gsiA1SortKey'][len('card/') :]
    assert before < pendulum.parse(created_at_str) < after
    assert card_item == {
        'partitionKey': 'card/cid',
        'sortKey': '-',
        'schemaVersion': 0,
        'gsiA1PartitionKey': 'user/uid',
        'gsiA1SortKey': f'card/{created_at_str}',
        'title': title,
        'action': action,
    }

    # verify we can't add that card again
    with pytest.raises(card_dynamo.client.exceptions.TransactionCanceledException):
        card_dynamo.client.transact_write_items([transact])


def test_transact_add_card_maximal(card_dynamo):
    card_id = 'cid'
    user_id = 'uid'
    title = 'you should know this'
    action = 'https://some-valid-url.com'
    sub_title = 'more info for you'
    created_at = pendulum.now('utc')
    notify_user_at = pendulum.now('utc')

    # add the card to the DB
    transact = card_dynamo.transact_add_card(
        card_id, user_id, title, action, sub_title=sub_title, created_at=created_at, notify_user_at=notify_user_at
    )
    card_dynamo.client.transact_write_items([transact])

    # retrieve the card and verify the format is as we expect
    card_item = card_dynamo.get_card(card_id)
    assert card_item == {
        'partitionKey': 'card/cid',
        'sortKey': '-',
        'schemaVersion': 0,
        'gsiA1PartitionKey': 'user/uid',
        'gsiA1SortKey': f'card/{created_at.to_iso8601_string()}',
        'title': title,
        'action': action,
        'subTitle': sub_title,
        'gsiK1PartitionKey': 'card',
        'gsiK1SortKey': notify_user_at.to_iso8601_string(),
    }


def test_clear_notify_user_at(card_dynamo):
    # add a card with a notify_user_at, verify
    card_id = str(uuid4())
    transact = card_dynamo.transact_add_card(card_id, 'uid', 't', 'a', notify_user_at=pendulum.now('utc'))
    card_dynamo.client.transact_write_items([transact])
    org_card_item = card_dynamo.get_card(card_id)
    assert 'gsiK1PartitionKey' in org_card_item
    assert 'gsiK1SortKey' in org_card_item

    # clear notify user at, verify
    card_item = card_dynamo.clear_notify_user_at(card_id)
    assert 'gsiK1PartitionKey' not in card_item
    assert 'gsiK1SortKey' not in card_item
    assert org_card_item.pop('gsiK1PartitionKey')
    assert org_card_item.pop('gsiK1SortKey')
    assert card_item == org_card_item
    assert card_dynamo.get_card(card_id) == card_item

    # clear notify user at, verify idempotent
    assert card_dynamo.clear_notify_user_at(card_id) == card_item
    assert card_dynamo.get_card(card_id) == card_item


def test_transact_delete_card(card_dynamo):
    # cant delelte card that DNE
    card_id = 'cid'
    transact = card_dynamo.transact_delete_card(card_id)
    with pytest.raises(card_dynamo.client.exceptions.TransactionCanceledException):
        card_dynamo.client.transact_write_items([transact])

    # add the card
    transact = card_dynamo.transact_add_card(card_id, 'uid', 'title', 'https://go.go')
    card_dynamo.client.transact_write_items([transact])

    # verify we can see the card in the DB
    assert card_dynamo.get_card(card_id)

    # delete the card
    transact = card_dynamo.transact_delete_card(card_id)
    card_dynamo.client.transact_write_items([transact])

    # verify the card is no longer in the db
    assert card_dynamo.get_card(card_id) is None


def test_generate_cards_by_user(card_dynamo):
    user_id = 'uid'

    # add a card by an unrelated user
    transact = card_dynamo.transact_add_card('coid', 'uoid', 'title', 'https://a.b')
    card_dynamo.client.transact_write_items([transact])

    # user has no cards, generate them
    assert list(card_dynamo.generate_cards_by_user(user_id)) == []

    # add one card
    transact = card_dynamo.transact_add_card('cid1', user_id, 'title1', 'https://a.b')
    card_dynamo.client.transact_write_items([transact])

    # generate the one card
    card_items = list(card_dynamo.generate_cards_by_user(user_id))
    assert len(card_items) == 1
    assert card_items[0]['partitionKey'] == 'card/cid1'
    assert card_items[0]['title'] == 'title1'

    # add another card
    transact = card_dynamo.transact_add_card('cid2', user_id, 'title2', 'https://c.d')
    card_dynamo.client.transact_write_items([transact])

    # generate two cards, check order
    card_items = list(card_dynamo.generate_cards_by_user(user_id))
    assert len(card_items) == 2
    assert card_items[0]['partitionKey'] == 'card/cid1'
    assert card_items[0]['title'] == 'title1'
    assert card_items[1]['partitionKey'] == 'card/cid2'
    assert card_items[1]['title'] == 'title2'

    # generate two cards, pks_only
    card_items = list(card_dynamo.generate_cards_by_user(user_id, pks_only=True))
    assert len(card_items) == 2
    assert card_items[0] == {'partitionKey': 'card/cid1', 'sortKey': '-'}
    assert card_items[1] == {'partitionKey': 'card/cid2', 'sortKey': '-'}


def test_generate_card_ids_by_notify_user_at(card_dynamo):
    # add a card with no user notification
    transact = card_dynamo.transact_add_card('coid', 'uoid', 'title', 'https://a.b')
    card_dynamo.client.transact_write_items([transact])

    # generate no cards
    card_ids = list(card_dynamo.generate_card_ids_by_notify_user_at(pendulum.now('utc')))
    assert card_ids == []

    # add one card
    card_id_1 = str(uuid4())
    notify_user_at_1 = pendulum.now('utc')
    transact = card_dynamo.transact_add_card(
        card_id_1, 'uid', 'title1', 'https://a.b', notify_user_at=notify_user_at_1
    )
    card_dynamo.client.transact_write_items([transact])

    # dont generate the card
    card_ids = list(
        card_dynamo.generate_card_ids_by_notify_user_at(notify_user_at_1 - pendulum.duration(microseconds=1))
    )
    assert card_ids == []

    # generate the card
    card_ids = list(card_dynamo.generate_card_ids_by_notify_user_at(notify_user_at_1))
    assert card_ids == [card_id_1]

    # add another card
    card_id_2 = str(uuid4())
    notify_user_at_2 = notify_user_at_1 + pendulum.duration(minutes=1)
    transact = card_dynamo.transact_add_card(
        card_id_2, 'uid2', 'title2', 'https://c.d', notify_user_at=notify_user_at_2
    )
    card_dynamo.client.transact_write_items([transact])

    # don't generate either card
    card_ids = list(
        card_dynamo.generate_card_ids_by_notify_user_at(notify_user_at_1 - pendulum.duration(microseconds=1))
    )
    assert card_ids == []

    # generate just one card
    card_ids = list(card_dynamo.generate_card_ids_by_notify_user_at(notify_user_at_1 + pendulum.duration(seconds=1)))
    assert card_ids == [card_id_1]

    # generate both cards, check order
    card_ids = list(card_dynamo.generate_card_ids_by_notify_user_at(notify_user_at_1 + pendulum.duration(minutes=2)))
    assert card_ids == [card_id_1, card_id_2]
