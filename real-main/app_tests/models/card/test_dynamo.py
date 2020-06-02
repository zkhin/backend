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
    now = pendulum.now('utc')

    # add the card to the DB
    transact = card_dynamo.transact_add_card(card_id, user_id, title, action, sub_title=sub_title, now=now)
    card_dynamo.client.transact_write_items([transact])

    # retrieve the card and verify the format is as we expect
    card_item = card_dynamo.get_card(card_id)
    assert card_item == {
        'partitionKey': 'card/cid',
        'sortKey': '-',
        'schemaVersion': 0,
        'gsiA1PartitionKey': 'user/uid',
        'gsiA1SortKey': f'card/{now.to_iso8601_string()}',
        'title': title,
        'action': action,
        'subTitle': sub_title,
    }


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
