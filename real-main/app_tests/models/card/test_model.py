import pytest
import uuid


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username=user_id)
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


def test_delete(card, user):
    # verify starting state
    assert card.dynamo.get_card(card.id)
    user.refresh_item().item.get('cardCount', 0) == 1

    # delete the card
    card.delete()

    # verify final state
    assert card.dynamo.get_card(card.id) is None
    user.refresh_item().item.get('cardCount', 0) == 0
