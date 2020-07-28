import random
from unittest.mock import call, patch
from uuid import uuid4

import pendulum
import pytest

from app.models.card import specs
from app.models.card.exceptions import CardAlreadyExists
from app.models.post.enums import PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user
user3 = user


@pytest.fixture
def chat_card_spec(user):
    yield specs.ChatCardSpec(user.id, chats_with_unviewed_messages_count=2)


@pytest.fixture
def requested_followers_card_spec(user):
    yield specs.RequestedFollowersCardSpec(user.id, requested_followers_count=3)


@pytest.fixture
def post(user, post_manager):
    yield post_manager.add_post(user, str(uuid4()), PostType.TEXT_ONLY, text='go go')


@pytest.fixture
def comment_card_spec(user, post):
    yield specs.CommentCardSpec(user.id, post.id, unviewed_comments_count=4)


@pytest.fixture
def post_likes_card_spec(user, post):
    yield specs.PostLikesCardSpec(user.id, post.id)


@pytest.fixture
def post_views_card_spec(user, post):
    yield specs.PostViewsCardSpec(user.id, post.id)


post1 = post
post2 = post


def test_add_card_minimal(card_manager, user):
    # add card
    before = pendulum.now('utc')
    title, action = 'card title', 'https://action'
    card = card_manager.add_card(user.id, title, action)
    after = pendulum.now('utc')

    # check final state
    assert card_manager.get_card(card.id)
    assert before < card.created_at < after
    assert card.user_id == user.id
    assert card.item['title'] == title
    assert card.item['action'] == action
    assert 'subTitle' not in card.item

    # verify can add another card with same title and action
    assert card_manager.add_card(user.id, title, action)

    # verify can't another card with same cardId
    with pytest.raises(CardAlreadyExists):
        card_manager.add_card(user.id, title, action, card.id)


def test_add_card_maximal(card_manager, user):
    card_id = 'cid'
    title, sub_title, action = 'card title', 'sub', 'https://action'
    created_at = pendulum.now('utc')
    notify_user_at = pendulum.now('utc')

    # check starting state
    assert card_manager.get_card(card_id) is None

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
    assert card_manager.get_card(card.id)


@pytest.mark.parametrize(
    'spec', pytest.lazy_fixture(['chat_card_spec', 'comment_card_spec', 'requested_followers_card_spec']),
)
def test_add_or_update_card_by_spec(user, spec, card_manager):
    # verify starting state
    assert card_manager.get_card(spec.card_id) is None

    # add the card, verify state
    before = pendulum.now('utc')
    card_manager.add_or_update_card_by_spec(spec)
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
    card_manager.add_or_update_card_by_spec(spec)
    new_card = card_manager.get_card(spec.card_id)
    assert new_card.id == spec.card_id
    assert new_card.item['title'] == spec.title
    assert new_card.item['action'] == spec.action
    assert new_card.created_at == card.created_at


@pytest.mark.parametrize('spec', pytest.lazy_fixture(['post_likes_card_spec', 'post_views_card_spec']))
def test_add_or_update_card_by_spec_with_only_usernames(user, spec, card_manager):
    # verify starting state
    assert card_manager.get_card(spec.card_id) is None

    # verify the only_usernames prevents us from ading the card
    assert card_manager.add_or_update_card_by_spec(spec) is None
    assert card_manager.get_card(spec.card_id) is None

    # add the card, verify state
    before = pendulum.now('utc')
    with patch.object(spec, 'only_usernames', (user.username,)):
        assert card_manager.add_or_update_card_by_spec(spec)
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
    with patch.object(spec, 'only_usernames', (user.username,)):
        assert card_manager.add_or_update_card_by_spec(spec)
    new_card = card_manager.get_card(spec.card_id)
    assert new_card.id == spec.card_id
    assert new_card.item['title'] == spec.title
    assert new_card.item['action'] == spec.action
    assert new_card.created_at == card.created_at

    # delete the card, verify it's gone
    card_manager.dynamo.delete_card(spec.card_id)
    assert card_manager.get_card(spec.card_id) is None

    # add the card again, this time with None for only_usernames
    with patch.object(spec, 'only_usernames', None):
        assert card_manager.add_or_update_card_by_spec(spec)
    assert card_manager.get_card(spec.card_id)


def test_comment_cards_are_per_post(user, card_manager, post1, post2):
    spec1 = specs.CommentCardSpec(user.id, post1.id, unviewed_comments_count=4)
    spec2 = specs.CommentCardSpec(user.id, post2.id, unviewed_comments_count=3)

    # verify starting state
    assert card_manager.get_card(spec1.card_id) is None
    assert card_manager.get_card(spec2.card_id) is None

    # add the card, verify state
    card_manager.add_or_update_card_by_spec(spec1)
    assert card_manager.get_card(spec1.card_id)
    assert card_manager.get_card(spec2.card_id) is None

    # add the other card, verify state and no conflict
    card_manager.add_or_update_card_by_spec(spec2)
    assert card_manager.get_card(spec1.card_id)
    assert card_manager.get_card(spec2.card_id)


def test_delete_post_cards(card_manager, comment_card_spec, post_likes_card_spec, post_views_card_spec, post):
    # set the user up with one of the only_usernames if needed
    card_specs = (comment_card_spec, post_likes_card_spec, post_views_card_spec)
    only_usernames = set.intersection(
        *[set(spec.only_usernames) for spec in card_specs if getattr(spec, 'only_usernames', [])]
    )
    if only_usernames:
        post.user.dynamo.update_user_username(
            post.user.id, random.choice(tuple(only_usernames)), post.user.username
        )

    # add them all to the DB, verify starting state
    for spec in card_specs:
        card_manager.add_or_update_card_by_spec(spec)
        assert card_manager.get_card(spec.card_id)

    # delete them all, verify new state
    card_manager.delete_post_cards(post.user_id, post.id)
    for spec in card_specs:
        assert card_manager.get_card(spec.card_id) is None

    # delete all again, verify idempotent
    card_manager.delete_post_cards(post.user_id, post.id)
    for spec in card_specs:
        assert card_manager.get_card(spec.card_id) is None


def test_notify_users(card_manager, pinpoint_client, user, user2):
    # configure mock to claim all apns-sending attempts succeeded
    pinpoint_client.configure_mock(**{'send_user_apns.return_value': True})

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
    assert card3.refresh_item().notify_user_at is None

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
    assert card4.refresh_item().notify_user_at is None
    assert card5.refresh_item().notify_user_at is None


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


def test_notify_users_only_usernames(card_manager, pinpoint_client, user, user2, user3):
    # configure mock to claim all apns-sending attempts succeeded
    pinpoint_client.configure_mock(**{'send_user_apns.return_value': True})

    # add one notification for each user in immediate past, verify they're there
    now = pendulum.now('utc')
    card1 = card_manager.add_card(user.id, 't1', 'https://a1', notify_user_at=now - pendulum.duration(seconds=2))
    card2 = card_manager.add_card(user2.id, 't2', 'https://a2', notify_user_at=now - pendulum.duration(seconds=1))
    card3 = card_manager.add_card(user3.id, 't3', 'https://a3', notify_user_at=now)
    assert card1.refresh_item().notify_user_at
    assert card2.refresh_item().notify_user_at
    assert card3.refresh_item().notify_user_at

    # run notificiations for just two of the users, verify just those two sent
    pinpoint_client.reset_mock()
    cnts = card_manager.notify_users(only_usernames=[user.username, user3.username])
    assert cnts == (2, 2)
    assert pinpoint_client.mock_calls == [
        call.send_user_apns(user.id, 'https://a1', 't1', body=None),
        call.send_user_apns(user3.id, 'https://a3', 't3', body=None),
    ]
    assert card1.refresh_item().notify_user_at is None
    assert card2.refresh_item().notify_user_at
    assert card3.refresh_item().notify_user_at is None

    # re-add those cards for which we just sent notificaitons
    card_manager.dynamo.delete_card(card1.id)
    card_manager.dynamo.delete_card(card3.id)
    card1 = card_manager.add_card(user.id, 't1', 'https://a1', notify_user_at=now - pendulum.duration(seconds=2))
    card3 = card_manager.add_card(user3.id, 't3', 'https://a3', notify_user_at=now)
    assert card1.refresh_item().notify_user_at
    assert card3.refresh_item().notify_user_at

    # run notificiations for just one of the user, verify just that one sent
    pinpoint_client.reset_mock()
    cnts = card_manager.notify_users(only_usernames=[user2.username])
    assert cnts == (1, 1)
    assert pinpoint_client.mock_calls == [
        call.send_user_apns(user2.id, 'https://a2', 't2', body=None),
    ]
    assert card1.refresh_item().notify_user_at
    assert card2.refresh_item().notify_user_at is None
    assert card3.refresh_item().notify_user_at

    # re-add a cards for which we just sent notificaitons
    card_manager.dynamo.delete_card(card2.id)
    card2 = card_manager.add_card(user2.id, 't2', 'https://a2', notify_user_at=now - pendulum.duration(seconds=1))
    assert card2.refresh_item().notify_user_at

    # run notificiations for no users, verify none sent
    pinpoint_client.reset_mock()
    cnts = card_manager.notify_users(only_usernames=[])
    assert cnts == (0, 0)
    assert pinpoint_client.mock_calls == []
    assert card1.refresh_item().notify_user_at
    assert card2.refresh_item().notify_user_at
    assert card3.refresh_item().notify_user_at

    # run notificiations for all users, verify all sent
    pinpoint_client.reset_mock()
    cnts = card_manager.notify_users()
    assert cnts == (3, 3)
    assert pinpoint_client.mock_calls == [
        call.send_user_apns(user.id, 'https://a1', 't1', body=None),
        call.send_user_apns(user2.id, 'https://a2', 't2', body=None),
        call.send_user_apns(user3.id, 'https://a3', 't3', body=None),
    ]
    assert card1.refresh_item().notify_user_at is None
    assert card2.refresh_item().notify_user_at is None
    assert card3.refresh_item().notify_user_at is None
