from uuid import uuid4

import pytest

from app.models.card.specs import ChatCardSpec, RequestedFollowersCardSpec


@pytest.fixture
def handle_requested_followers_card(user_manager):
    yield user_manager.postprocessor.handle_requested_followers_card


@pytest.fixture
def handle_chats_with_new_messages_card(user_manager):
    yield user_manager.postprocessor.handle_chats_with_new_messages_card


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def requested_followers_card_spec(user):
    yield RequestedFollowersCardSpec(user.id)


@pytest.fixture
def chats_with_new_messages_card_spec(user):
    yield ChatCardSpec(user.id)


@pytest.mark.parametrize('old_count, new_count', [[None, None], [0, 0], [None, 0], [2, 2]])
@pytest.mark.parametrize(
    'handle_method, attribute_name, card_spec',
    [
        [
            pytest.lazy_fixture('handle_requested_followers_card'),
            'followersRequestedCount',
            pytest.lazy_fixture('requested_followers_card_spec'),
        ],
        [
            pytest.lazy_fixture('handle_chats_with_new_messages_card'),
            'chatsWithUnviewedMessagesCount',
            pytest.lazy_fixture('chats_with_new_messages_card_spec'),
        ],
    ],
)
def test_handle_card_no_change(
    handle_method, card_manager, user, attribute_name, card_spec, old_count, new_count
):
    old_item = {'userId': user.id}
    if old_count is not None:
        old_item[attribute_name] = old_count
    new_item = {'userId': user.id}
    if new_count is not None:
        new_item[attribute_name] = new_count
    assert card_manager.get_card(card_spec.card_id) is None

    # postprocess, verify no change in DB state
    handle_method(user.id, old_item, new_item)
    assert card_manager.get_card(card_spec.card_id) is None


@pytest.mark.parametrize(
    'handle_method, attribute_name, card_spec',
    [
        [
            pytest.lazy_fixture('handle_requested_followers_card'),
            'followersRequestedCount',
            pytest.lazy_fixture('requested_followers_card_spec'),
        ],
        [
            pytest.lazy_fixture('handle_chats_with_new_messages_card'),
            'chatsWithUnviewedMessagesCount',
            pytest.lazy_fixture('chats_with_new_messages_card_spec'),
        ],
    ],
)
def test_handle_card_increment_decrements(handle_method, card_manager, user, card_spec, attribute_name):
    old_item = {'userId': user.id}
    new_item = {'userId': user.id, attribute_name: 2}
    assert card_manager.get_card(card_spec.card_id) is None

    # increment above zero, verify card is added to the db
    handle_method(user.id, old_item, new_item)
    card = card_manager.get_card(card_spec.card_id)
    assert card.spec.card_id == card_spec.card_id
    old_card = card

    # increment again, verify title changes
    old_item = new_item
    new_item = {'userId': user.id, attribute_name: 3}
    handle_method(user.id, old_item, new_item)
    card = card_manager.get_card(card_spec.card_id)
    assert card.spec.card_id == card_spec.card_id
    assert card.item['title'] != old_card.item['title']
    old_card = card

    # decrement stay above zero, verify title changes
    old_item = new_item
    new_item = {'userId': user.id, attribute_name: 1}
    handle_method(user.id, old_item, new_item)
    card = card_manager.get_card(card_spec.card_id)
    assert card.spec.card_id == card_spec.card_id
    assert card.item['title'] != old_card.item['title']
    old_card = card

    # decrement to zero, verify disappears
    old_item = new_item
    new_item = {'userId': user.id, attribute_name: 0}
    handle_method(user.id, old_item, new_item)
    assert card_manager.get_card(card_spec.card_id) is None

    # increment above zero again, verify reappears
    old_item = new_item
    new_item = {'userId': user.id, attribute_name: 1}
    handle_method(user.id, old_item, new_item)
    assert card_manager.get_card(card_spec.card_id).spec.card_id == card_spec.card_id
