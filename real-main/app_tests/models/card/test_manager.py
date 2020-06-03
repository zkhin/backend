import uuid

import pendulum
import pytest

from app.models.card import enums


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


def test_add_card_minimal(card_manager, user, appsync_client):
    # check starting state
    appsync_client.reset_mock()
    assert user.refresh_item().item.get('cardCount', 0) == 0

    # add card
    before = pendulum.now('utc')
    title, action = 'card title', 'https://action'
    card = card_manager.add_card(user.id, title, action)
    after = pendulum.now('utc')

    # check final state
    assert user.refresh_item().item.get('cardCount', 0) == 1
    assert card_manager.get_card(card.id)
    assert before < card.created_at < after
    assert card.user_id == user.id
    assert card.item['title'] == title
    assert card.item['action'] == action
    assert 'subTitle' not in card.item

    # check the notifiation was triggered
    assert len(appsync_client.mock_calls) == 1
    assert 'triggerCardNotification' in str(appsync_client.send.call_args.args[0])
    assert appsync_client.send.call_args.args[1]['input']['type'] == enums.CardNotificationType.ADDED
    assert appsync_client.send.call_args.args[1]['input']['cardId'] == card.id

    # verify can add another card with same title and action
    assert card_manager.add_card(user.id, title, action)

    # verify can't another card with same cardId
    with pytest.raises(card_manager.exceptions.CardAlreadyExists):
        card_manager.add_card(user.id, title, action, card.id)


def test_add_card_maximal(card_manager, user):
    card_id = 'cid'
    title, sub_title, action = 'card title', 'sub', 'https://action'
    now = pendulum.now('utc')

    # check starting state
    assert card_manager.get_card(card_id) is None
    assert user.refresh_item().item.get('cardCount', 0) == 0

    # add card, check format
    card = card_manager.add_card(user.id, title, action, card_id=card_id, sub_title=sub_title, now=now)
    assert card.id == card_id
    assert card.user_id == user.id
    assert card.created_at == now
    assert card.item['title'] == title
    assert card.item['action'] == action
    assert card.item['subTitle'] == sub_title

    # check final state
    assert user.refresh_item().item.get('cardCount', 0) == 1
    assert card_manager.get_card(card.id)


@pytest.mark.parametrize('wk_card', [enums.COMMENT_ACTIVITY_CARD, enums.CHAT_ACTIVITY_CARD])
def test_add_and_remove_well_known_card(user, wk_card, card_manager):
    card_id = f'{user.id}:{wk_card.name}'

    # verify starting state
    assert card_manager.get_card(card_id) is None

    # add the card, verify state
    before = pendulum.now('utc')
    card_manager.add_well_known_card_if_dne(user.id, wk_card)
    after = pendulum.now('utc')
    card = card_manager.get_card(card_id)
    assert card.id == card_id
    assert card.item['title'] == wk_card.title
    assert card.item['action'] == wk_card.action
    assert before < card.created_at < after

    # add the card again, verify no-op
    card_manager.add_well_known_card_if_dne(user.id, wk_card)
    new_card = card_manager.get_card(card_id)
    assert new_card.id == card_id
    assert new_card.item['title'] == wk_card.title
    assert new_card.item['action'] == wk_card.action
    assert new_card.created_at == card.created_at

    # remove the card, verify it's gone
    card_manager.remove_well_known_card_if_exists(user.id, wk_card)
    assert card_manager.get_card(card_id) is None

    # remove the card again, verify no-op
    card_manager.remove_well_known_card_if_exists(user.id, wk_card)
    assert card_manager.get_card(card_id) is None


def test_truncate_cards(card_manager, user):
    # verify starting state
    assert list(card_manager.dynamo.generate_cards_by_user(user.id)) == []
    assert user.refresh_item().item.get('cardCount', 0) == 0

    # test truncate with no cards
    card_manager.truncate_cards(user.id)
    assert list(card_manager.dynamo.generate_cards_by_user(user.id)) == []
    assert user.refresh_item().item.get('cardCount', 0) == 0

    # add two cards
    card_id_1, card_id_2 = 'cid1', 'cid2'
    card_manager.add_card(user.id, 't1', 'https://a1', card_id=card_id_1)
    card_manager.add_card(user.id, 't2', 'https://a1', card_id=card_id_2)

    # verify we see those cards
    cards = list(card_manager.dynamo.generate_cards_by_user(user.id))
    assert len(cards) == 2
    assert cards[0]['partitionKey'] == 'card/cid1'
    assert cards[1]['partitionKey'] == 'card/cid2'
    assert user.refresh_item().item.get('cardCount', 0) == 2

    # test truncate the cards, verify they have disappeared but user count is unchanged
    card_manager.truncate_cards(user.id)
    assert list(card_manager.dynamo.generate_cards_by_user(user.id)) == []
    assert card_manager.get_card(card_id_1) is None
    assert card_manager.get_card(card_id_2) is None
    assert user.refresh_item().item.get('cardCount', 0) == 2
