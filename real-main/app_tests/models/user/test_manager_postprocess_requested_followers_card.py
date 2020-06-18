from uuid import uuid4

import pytest

from app.models.card.specs import RequestedFollowersCardSpec


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def card_spec(user):
    yield RequestedFollowersCardSpec(user.id)


@pytest.mark.parametrize('old_count, new_count', [[None, None], ['0', '0'], [None, '0'], ['2', '1'], ['2', '2']])
@pytest.mark.parametrize('card_exists', [True, False])
def test_postprocess_requested_followers_card_no_change(
    user_manager, card_manager, user, card_spec, old_count, new_count, card_exists
):
    old_item = {'userId': {'S': user.id}}
    if old_count is not None:
        old_item['requestedFollowerCount'] = {'N': old_count}
    new_item = {'userId': {'S': user.id}}
    if new_count is not None:
        new_item['requestedFollowerCount'] = {'N': new_count}

    if card_exists:
        card_manager.add_card_by_spec_if_dne(card_spec)
        assert card_manager.get_card(card_spec.card_id)
    else:
        assert card_manager.get_card(card_spec.card_id) is None

    # postprocess, verify no change in DB state
    user_manager.postprocess_requested_followers_card(user.id, old_item, new_item)
    if card_exists:
        assert card_manager.get_card(card_spec.card_id)
    else:
        assert card_manager.get_card(card_spec.card_id) is None


def test_postprocess_requested_followers_card_increment_decrements(user_manager, card_manager, user, card_spec):
    old_item = {'userId': {'S': user.id}}
    new_item = {'userId': {'S': user.id}, 'requestedFollowerCount': {'N': '2'}}
    assert card_manager.get_card(card_spec.card_id) is None

    # increment above zero, verify card is added to the db
    user_manager.postprocess_requested_followers_card(user.id, old_item, new_item)
    assert card_manager.get_card(card_spec.card_id).spec == card_spec

    # increment again, verify no change
    old_item = new_item
    new_item = {'userId': {'S': user.id}, 'requestedFollowerCount': {'N': '3'}}
    user_manager.postprocess_requested_followers_card(user.id, old_item, new_item)
    assert card_manager.get_card(card_spec.card_id).spec == card_spec

    # decrement stay above zero, verify no change
    old_item = new_item
    new_item = {'userId': {'S': user.id}, 'requestedFollowerCount': {'N': '1'}}
    user_manager.postprocess_requested_followers_card(user.id, old_item, new_item)
    assert card_manager.get_card(card_spec.card_id).spec == card_spec

    # decrement to zero, verify disappears
    old_item = new_item
    new_item = {'userId': {'S': user.id}, 'requestedFollowerCount': {'N': '0'}}
    user_manager.postprocess_requested_followers_card(user.id, old_item, new_item)
    assert card_manager.get_card(card_spec.card_id) is None

    # increment above zero again, verify reappears
    old_item = new_item
    new_item = {'userId': {'S': user.id}, 'requestedFollowerCount': {'N': '1'}}
    user_manager.postprocess_requested_followers_card(user.id, old_item, new_item)
    assert card_manager.get_card(card_spec.card_id).spec == card_spec
