from unittest.mock import Mock, call
from uuid import uuid4

import pytest

from app.models.card.enums import CardNotificationType


@pytest.fixture
def card_postprocessor(card_manager):
    yield card_manager.postprocessor


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def card(user, card_manager):
    yield card_manager.add_card(user.id, 'card title', 'https://action')


def test_run(card_postprocessor, card, user):
    card_postprocessor.send_gql_notifications = Mock(card_postprocessor.send_gql_notifications)
    pk, sk = card.item['partitionKey'], card.item['sortKey']
    old_item, new_item = {}, {}

    # call with an item that's not the base item, check mocks
    card_postprocessor.run(pk, 'something-else', old_item, new_item)
    assert card_postprocessor.send_gql_notifications.call_count == 0

    # call with the base item, check mocks
    card_postprocessor.run(pk, sk, old_item, new_item)
    assert card_postprocessor.send_gql_notifications.mock_calls == [call(old_item, new_item)]


def test_send_gql_notifications(card_postprocessor, card, user, caplog, appsync_client):
    assert 'cardCount' not in user.refresh_item().item

    # simulate adding
    appsync_client.reset_mock()
    card_postprocessor.send_gql_notifications({}, card.item)
    assert len(appsync_client.mock_calls) == 1
    assert 'triggerCardNotification' in str(appsync_client.send.call_args.args[0])
    assert appsync_client.send.call_args.args[1]['input']['type'] == CardNotificationType.ADDED
    assert appsync_client.send.call_args.args[1]['input']['cardId'] == card.id

    # simulate editing
    appsync_client.reset_mock()
    card_postprocessor.send_gql_notifications(card.item, card.item)
    assert 'triggerCardNotification' in str(appsync_client.send.call_args.args[0])
    assert appsync_client.send.call_args.args[1]['input']['type'] == CardNotificationType.EDITED
    assert appsync_client.send.call_args.args[1]['input']['cardId'] == card.id

    # simulate deleting
    appsync_client.reset_mock()
    card_postprocessor.send_gql_notifications(card.item, {})
    assert len(appsync_client.mock_calls) == 1
    assert 'triggerCardNotification' in str(appsync_client.send.call_args.args[0])
    assert appsync_client.send.call_args.args[1]['input']['type'] == CardNotificationType.DELETED
    assert appsync_client.send.call_args.args[1]['input']['cardId'] == card.id
