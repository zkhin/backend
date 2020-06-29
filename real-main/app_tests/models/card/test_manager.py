from unittest.mock import call
from uuid import uuid4

import pendulum
import pytest

from app.models.card import enums, specs
from app.models.post.enums import PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user


@pytest.fixture
def chat_card_spec(user):
    yield specs.ChatCardSpec(user.id)


@pytest.fixture
def requested_followers_card_spec(user):
    yield specs.RequestedFollowersCardSpec(user.id)


@pytest.fixture
def comment_card_spec(user, post_manager):
    post = post_manager.add_post(user, str(uuid4()), PostType.TEXT_ONLY, text='go go')
    yield specs.CommentCardSpec(user.id, post.id)


comment_card_spec1 = comment_card_spec
comment_card_spec2 = comment_card_spec


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
    created_at = pendulum.now('utc')
    notify_user_at = pendulum.now('utc')

    # check starting state
    assert card_manager.get_card(card_id) is None
    assert user.refresh_item().item.get('cardCount', 0) == 0

    # add card, check format
    card = card_manager.add_card(
        user.id,
        title,
        action,
        card_id=card_id,
        sub_title=sub_title,
        created_at=created_at,
        notify_user_at=notify_user_at,
    )
    assert card.id == card_id
    assert card.user_id == user.id
    assert card.created_at == created_at
    assert card.notify_user_at == notify_user_at
    assert card.item['title'] == title
    assert card.item['action'] == action
    assert card.item['subTitle'] == sub_title

    # check final state
    assert user.refresh_item().item.get('cardCount', 0) == 1
    assert card_manager.get_card(card.id)


@pytest.mark.parametrize(
    'spec', pytest.lazy_fixture(['chat_card_spec', 'comment_card_spec', 'requested_followers_card_spec'])
)
def test_add_and_remove_card_by_spec(user, spec, card_manager):
    # verify starting state
    assert card_manager.get_card(spec.card_id) is None

    # add the card, verify state
    before = pendulum.now('utc')
    card_manager.add_card_by_spec_if_dne(spec)
    after = pendulum.now('utc')
    card = card_manager.get_card(spec.card_id)
    assert card.id == spec.card_id
    assert card.item['title'] == spec.title
    assert card.item['action'] == spec.action
    assert before < card.created_at < after
    if spec.notify_user_after:
        assert card.notify_user_at == card.created_at + spec.notify_user_after
    else:
        assert card.notify_user_at is None

    # add the card again, verify no-op
    card_manager.add_card_by_spec_if_dne(spec)
    new_card = card_manager.get_card(spec.card_id)
    assert new_card.id == spec.card_id
    assert new_card.item['title'] == spec.title
    assert new_card.item['action'] == spec.action
    assert new_card.created_at == card.created_at

    # remove the card, verify it's gone
    card_manager.remove_card_by_spec_if_exists(spec)
    assert card_manager.get_card(spec.card_id) is None

    # remove the card again, verify no-op
    card_manager.remove_card_by_spec_if_exists(spec)
    assert card_manager.get_card(spec.card_id) is None


def test_comment_cards_are_per_post(user, card_manager, comment_card_spec1, comment_card_spec2):
    spec1 = comment_card_spec1
    spec2 = comment_card_spec2

    # verify starting state
    assert card_manager.get_card(spec1.card_id) is None
    assert card_manager.get_card(spec2.card_id) is None

    # add the card, verify state
    card_manager.add_card_by_spec_if_dne(spec1)
    assert card_manager.get_card(spec1.card_id)
    assert card_manager.get_card(spec2.card_id) is None

    # add the other card, verify state and no conflict
    card_manager.add_card_by_spec_if_dne(spec2)
    assert card_manager.get_card(spec1.card_id)
    assert card_manager.get_card(spec2.card_id)


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


def test_notify_users(card_manager, pinpoint_client, user, user2):
    # add a card with a notification in the far future
    notify_user_at1 = pendulum.now('utc') + pendulum.duration(hours=1)
    card1 = card_manager.add_card(user.id, 'title', 'https://action', notify_user_at=notify_user_at1)
    assert card1.notify_user_at == notify_user_at1

    # run notificiations, verify none sent and no db changes
    cnts = card_manager.notify_users()
    assert cnts == (0, 0)
    assert pinpoint_client.mock_calls == []
    assert card1.item == card1.refresh_item().item

    # add another card with a notification in the immediate future
    notify_user_at2 = pendulum.now('utc') + pendulum.duration(seconds=1)
    card2 = card_manager.add_card(user.id, 'title', 'https://action', notify_user_at=notify_user_at2)
    assert card2.notify_user_at == notify_user_at2

    # run notificiations, verify none sent and no db changes
    cnts = card_manager.notify_users()
    assert cnts == (0, 0)
    assert pinpoint_client.mock_calls == []
    assert card1.item == card1.refresh_item().item
    assert card2.item == card2.refresh_item().item

    # add another card with a notification in the immediate past
    notify_user_at3 = pendulum.now('utc')
    card3 = card_manager.add_card(user.id, 'title3', 'https://action3', notify_user_at=notify_user_at3)
    assert card3.notify_user_at == notify_user_at3

    # run notificiations, verify one sent
    cnts = card_manager.notify_users()
    assert cnts == (1, 1)
    assert pinpoint_client.mock_calls == [
        call.send_user_apns(user.id, 'https://action3', 'title3', body=None),
    ]
    assert card1.item == card1.refresh_item().item
    assert card2.item == card2.refresh_item().item
    assert card3.refresh_item().item is None

    # two cards with a notification in past
    notify_user_at4 = pendulum.now('utc') - pendulum.duration(seconds=1)
    notify_user_at5 = pendulum.now('utc') - pendulum.duration(hours=1)
    card4 = card_manager.add_card(user.id, 'title4', 'https://a4', sub_title='s', notify_user_at=notify_user_at4)
    card5 = card_manager.add_card(user2.id, 'title5', 'https://a5', notify_user_at=notify_user_at5)
    assert card4.notify_user_at == notify_user_at4
    assert card5.notify_user_at == notify_user_at5

    # run notificiations, verify both sent
    pinpoint_client.reset_mock()
    cnts = card_manager.notify_users()
    assert cnts == (2, 2)
    assert pinpoint_client.mock_calls == [
        call.send_user_apns(user2.id, 'https://a5', 'title5', body=None),
        call.send_user_apns(user.id, 'https://a4', 'title4', body='s'),
    ]
    assert card1.item == card1.refresh_item().item
    assert card2.item == card2.refresh_item().item
    assert card4.refresh_item().item is None
    assert card5.refresh_item().item is None


def test_notify_users_failed_notification(card_manager, pinpoint_client, user):
    # add card with a notification in the immediate past
    notify_user_at = pendulum.now('utc')
    card = card_manager.add_card(user.id, 'title', 'https://action', notify_user_at=notify_user_at)
    assert card.notify_user_at == notify_user_at

    # configure our mock to report a failed message send
    pinpoint_client.configure_mock(**{'send_user_apns.return_value': False})

    # run notificiations, verify attempted send and correct DB changes upon failure
    cnts = card_manager.notify_users()
    assert cnts == (1, 0)
    assert pinpoint_client.mock_calls == [
        call.send_user_apns(user.id, 'https://action', 'title', body=None),
    ]
    org_item = card.item
    card.refresh_item()
    assert 'gsiK1PartitionKey' not in card.item
    assert 'gsiK1SortKey' not in card.item
    assert org_item.pop('gsiK1PartitionKey')
    assert org_item.pop('gsiK1SortKey')
    assert card.item == org_item
