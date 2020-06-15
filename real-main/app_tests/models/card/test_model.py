import uuid

import pytest

from app.models.card.enums import CardNotificationType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def card(user, card_manager):
    yield card_manager.add_card(user.id, 'card title', 'https://action')


def test_serialize(user, card):
    # serialize the card without a subtitle
    resp = card.serialize(user.id)
    assert resp['cardId'] == card.id
    assert resp['title'] == card.item['title']
    assert resp['action'] == card.item['action']
    assert 'subTitle' not in card.item

    # add a subtitle, serialize again
    card.item['subTitle'] = 'this is a sub'
    resp = card.serialize(user.id)
    assert resp['cardId'] == card.id
    assert resp['title'] == card.item['title']
    assert resp['action'] == card.item['action']
    assert resp['subTitle'] == card.item['subTitle']


def test_delete(card, user, appsync_client):
    appsync_client.reset_mock()

    # verify starting state
    assert card.dynamo.get_card(card.id)
    assert user.refresh_item().item.get('cardCount', 0) == 1

    # delete the card
    card.delete()

    # verify final state
    assert card.dynamo.get_card(card.id) is None
    assert user.refresh_item().item.get('cardCount', 0) == 0

    # check the notifiation was triggered
    assert len(appsync_client.mock_calls) == 1
    assert 'triggerCardNotification' in str(appsync_client.send.call_args.args[0])
    assert appsync_client.send.call_args.args[1]['input']['type'] == CardNotificationType.DELETED
    assert appsync_client.send.call_args.args[1]['input']['cardId'] == card.id
