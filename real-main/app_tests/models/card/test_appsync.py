import uuid

import pytest

from app.models.card.appsync import CardAppSync


@pytest.fixture
def card_appsync(appsync_client):
    yield CardAppSync(appsync_client)


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def minimal_card(card_manager, user):
    card_id = str(uuid.uuid4())
    yield card_manager.add_card(user.id, card_id, 'min_title', 'https://real.app/min/')


@pytest.fixture
def maximal_card(card_manager, user):
    card_id = str(uuid.uuid4())
    yield card_manager.add_card(user.id, card_id, 'max_title', 'https://real.app/max/', sub_title='my max card')


@pytest.mark.parametrize('card', (pytest.lazy_fixture('minimal_card'), pytest.lazy_fixture('maximal_card')))
def test_trigger_notification(card_appsync, user, card, appsync_client):
    appsync_client.reset_mock()

    # trigger, check client was called correctly
    card_appsync.trigger_notification('card-notif-type', card)
    assert len(appsync_client.mock_calls) == 1
    assert len(appsync_client.send.call_args.kwargs) == 0
    assert len(appsync_client.send.call_args.args) == 2
    assert 'triggerCardNotification' in str(appsync_client.send.call_args.args[0])
    assert appsync_client.send.call_args.args[1] == {
        'input': {
            'userId': user.id,
            'type': 'card-notif-type',
            'cardId': card.id,
            'title': card.item['title'],
            'subTitle': card.item.get('subTitle'),
            'action': card.item['action'],
        }
    }
