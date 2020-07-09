from uuid import uuid4

import pytest

from app.models.card.specs import ChatCardSpec, RequestedFollowersCardSpec


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def chat_card_spec(card_manager, user):
    spec = ChatCardSpec(user.id, chats_with_unviewed_messages_count=2)
    card_manager.add_or_update_card_by_spec(spec)
    yield spec


@pytest.fixture
def requested_followers_card_spec(card_manager, user):
    spec = RequestedFollowersCardSpec(user.id, requested_followers_count=3)
    card_manager.add_or_update_card_by_spec(spec)
    yield spec


@pytest.mark.parametrize('spec', pytest.lazy_fixture(['chat_card_spec', 'requested_followers_card_spec']))
def test_on_user_delete_removes_card_specs(card_manager, spec, user):
    # verify deletes the card
    assert card_manager.get_card(spec.card_id)
    card_manager.on_user_delete(user.id, user.item)
    assert card_manager.get_card(spec.card_id) is None

    # verify no error if card does not exist
    card_manager.on_user_delete(user.id, user.item)
    assert card_manager.get_card(spec.card_id) is None
