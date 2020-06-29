import logging
from uuid import uuid4

import pytest


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def card(user, card_manager):
    yield card_manager.add_card(user.id, 'card title', 'https://action')


def test_postprocess_record_card_added_edited_deleted(card_manager, card, user, caplog):
    typed_pk = card.dynamo.typed_pk(card.id)
    pk, sk = typed_pk['partitionKey']['S'], typed_pk['sortKey']['S']
    assert 'cardCount' not in user.refresh_item().item

    # simulate adding
    old_item = None
    new_item = card.dynamo.client.get_typed_item(typed_pk)
    card_manager.postprocess_record(pk, sk, old_item, new_item)
    assert user.refresh_item().item['cardCount'] == 1

    # simulate editing
    old_item = new_item
    new_item = card.dynamo.client.get_typed_item(typed_pk)
    card_manager.postprocess_record(pk, sk, old_item, new_item)
    assert user.refresh_item().item['cardCount'] == 1

    # simulate deleting
    old_item = new_item
    new_item = None
    card_manager.postprocess_record(pk, sk, old_item, new_item)
    assert user.refresh_item().item['cardCount'] == 0

    # simulate deleting again, verify fails softly
    with caplog.at_level(logging.WARNING):
        card_manager.postprocess_record(pk, sk, old_item, new_item)
    assert len(caplog.records) == 1
    assert 'Failed to decrement' in caplog.records[0].msg
    assert 'cardCount' in caplog.records[0].msg
    assert user.id in caplog.records[0].msg
    assert user.refresh_item().item['cardCount'] == 0
