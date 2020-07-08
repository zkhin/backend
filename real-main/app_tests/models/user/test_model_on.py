from unittest.mock import Mock, call
from uuid import uuid4

import pendulum
import pytest

from app.models.card.specs import ChatCardSpec, RequestedFollowersCardSpec
from app.models.user.enums import UserStatus


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.mark.parametrize(
    'attribute_name, method_name',
    [
        ['commentForcedDeletionCount', 'disable_by_forced_comment_deletions_if_necessary'],
        ['postForcedArchivingCount', 'disable_by_forced_post_archivings_if_necessary'],
        ['followersRequestedCount', 'refresh_requested_followers_card'],
        ['chatsWithUnviewedMessagesCount', 'refresh_chats_with_new_messages_card'],
    ],
)
@pytest.mark.parametrize(
    'calls, new_value, old_value',
    [
        [True, 1, None],
        [True, 1, 0],
        [True, None, 1],
        [True, 0, 2],
        [True, 3, 0],
        [False, None, 0],
        [False, 2, 2],
        [False, None, None],
    ],
)
def test_on_add_or_edit_calls_simple_count_change(user, attribute_name, method_name, new_value, old_value, calls):
    # configure state, check
    old_item = user.item.copy()
    if new_value is None:
        user.item.pop(attribute_name, None)
    else:
        user.item[attribute_name] = new_value
    if old_value is None:
        old_item.pop(attribute_name, None)
    else:
        old_item[attribute_name] = old_value
    assert user.item.get(attribute_name) == new_value
    assert old_item.get(attribute_name) == old_value

    # mock and then handle the event, check calls
    setattr(user, method_name, Mock(getattr(user, method_name)))
    user.on_add_or_edit(old_item)
    if calls:
        assert getattr(user, method_name).mock_calls == [call()]
    else:
        assert getattr(user, method_name).mock_calls == []


@pytest.mark.parametrize('dynamo_name, pinpoint_name', [['email', 'EMAIL'], ['phoneNumber', 'SMS']])
@pytest.mark.parametrize(
    'calls, new_value, old_value',
    [[True, 'aa', None], [True, 'bb', 'aa'], [True, None, 'bb'], [False, None, None], [False, 'aa', 'aa']],
)
def test_on_add_or_edit_calls_refresh_pinpoint_attribute(
    user, dynamo_name, pinpoint_name, new_value, old_value, calls
):
    # configure state, check
    old_item = user.item.copy()
    if new_value is None:
        user.item.pop(dynamo_name, None)
    else:
        user.item[dynamo_name] = new_value
    if old_value is None:
        old_item.pop(dynamo_name, None)
    else:
        old_item[dynamo_name] = old_value
    assert user.item.get(dynamo_name) == new_value
    assert old_item.get(dynamo_name) == old_value

    # mock and then handle the event, check calls
    user.refresh_pinpoint_attribute = Mock(user.refresh_pinpoint_attribute)
    user.on_add_or_edit(old_item)
    if calls:
        assert user.refresh_pinpoint_attribute.mock_calls == [call(pinpoint_name, dynamo_name)]
    else:
        assert user.refresh_pinpoint_attribute.mock_calls == []


@pytest.mark.parametrize(
    'calls, new_value, old_value',
    [
        [True, UserStatus.DISABLED, None],
        [True, UserStatus.DISABLED, UserStatus.ACTIVE],
        [True, None, UserStatus.DELETING],
        [True, UserStatus.DISABLED, UserStatus.DELETING],
        [False, None, None],
        [False, None, UserStatus.ACTIVE],
        [False, UserStatus.DISABLED, UserStatus.DISABLED],
    ],
)
def test_on_add_or_edit_calls_refresh_pinpoint_by_user_status(user, new_value, old_value, calls):
    # configure state, check
    old_item = user.item.copy()
    if new_value is None:
        user.item.pop('userStatus', None)
    else:
        user.item['userStatus'] = new_value
    if old_value is None:
        old_item.pop('userStatus', None)
    else:
        old_item['userStatus'] = old_value
    assert user.item.get('userStatus') == new_value
    assert old_item.get('userStatus') == old_value

    # mock and then handle the event, check calls
    user.refresh_pinpoint_by_user_status = Mock(user.refresh_pinpoint_by_user_status)
    user.on_add_or_edit(old_item)
    if calls:
        assert user.refresh_pinpoint_by_user_status.mock_calls == [call()]
    else:
        assert user.refresh_pinpoint_by_user_status.mock_calls == []


def test_on_add_or_edit_calls_elasticsearch_client(user):
    user.elasticsearch_client = Mock(user.elasticsearch_client)

    # no change
    old_item = user.item.copy()
    user.on_add_or_edit(old_item)
    assert user.elasticsearch_client.mock_calls == []

    # set full name
    old_item = user.item.copy()
    user.item['fullName'] = 'Mr Smith'
    user.elasticsearch_client.reset_mock()
    user.on_add_or_edit(old_item)
    assert user.elasticsearch_client.mock_calls == [call.put_user(user.id, user.username, 'Mr Smith')]

    # change username
    old_item = user.item.copy()
    user.item['username'] = 'new_username'
    user.elasticsearch_client.reset_mock()
    user.on_add_or_edit(old_item)
    assert user.elasticsearch_client.mock_calls == [call.put_user(user.id, 'new_username', 'Mr Smith')]

    # change both username and full name
    old_item = user.item.copy()
    user.item['username'] = 'newerusername'
    user.item.pop('fullName', None)
    user.elasticsearch_client.reset_mock()
    user.on_add_or_edit(old_item)
    assert user.elasticsearch_client.mock_calls == [call.put_user(user.id, 'newerusername', None)]

    # change manually reindexed timestamp (used to re-build the elastic search index)
    old_item = user.item.copy()
    user.item['lastManuallyReindexedAt'] = pendulum.now('utc').to_iso8601_string()
    user.elasticsearch_client.reset_mock()
    user.on_add_or_edit(old_item)
    assert user.elasticsearch_client.mock_calls == [call.put_user(user.id, 'newerusername', None)]

    # change manually reindexed timestamp again
    old_item = user.item.copy()
    user.item['lastManuallyReindexedAt'] = pendulum.now('utc').to_iso8601_string()
    user.elasticsearch_client.reset_mock()
    user.on_add_or_edit(old_item)
    assert user.elasticsearch_client.mock_calls == [call.put_user(user.id, 'newerusername', None)]


def test_on_delete(user):
    # configure mocks
    user.card_manager = Mock(user.card_manager)
    user.elasticsearch_client = Mock(user.elasticsearch_client)
    user.pinpoint_client = Mock(user.pinpoint_client)

    # handle delete event, check mock calls
    user.on_delete()
    assert user.elasticsearch_client.mock_calls == [call.delete_user(user.id)]
    assert user.pinpoint_client.mock_calls == [call.delete_user_endpoints(user.id)]
    assert len(user.card_manager.mock_calls) == 2
    card_spec1 = user.card_manager.mock_calls[0].args[0]
    assert card_spec1.card_id == ChatCardSpec(user.id).card_id
    card_spec2 = user.card_manager.mock_calls[1].args[0]
    assert card_spec2.card_id == RequestedFollowersCardSpec(user.id).card_id
    assert user.card_manager.mock_calls == [
        call.remove_card_by_spec_if_exists(card_spec1),
        call.remove_card_by_spec_if_exists(card_spec2),
    ]
