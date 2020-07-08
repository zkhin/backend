from unittest.mock import Mock, call
from uuid import uuid4

import pytest

from app.models.card.specs import CommentCardSpec
from app.models.post.enums import PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user, 'pid1', PostType.TEXT_ONLY, text='t')


@pytest.mark.parametrize(
    'attribute_name, method_name', [['commentsUnviewedCount', 'refresh_comments_card']],
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
def test_on_add_or_edit_calls_simple_count_change(post, attribute_name, method_name, new_value, old_value, calls):
    # configure state, check
    old_item = post.item.copy()
    if new_value is None:
        post.item.pop(attribute_name, None)
    else:
        post.item[attribute_name] = new_value
    if old_value is None:
        old_item.pop(attribute_name, None)
    else:
        old_item[attribute_name] = old_value
    assert post.item.get(attribute_name) == new_value
    assert old_item.get(attribute_name) == old_value

    # mock and then handle the event, check calls
    setattr(post, method_name, Mock(getattr(post, method_name)))
    post.on_add_or_edit(old_item)
    if calls:
        assert getattr(post, method_name).mock_calls == [call()]
    else:
        assert getattr(post, method_name).mock_calls == []


def test_on_delete(post):
    # configure mocks
    post.card_manager = Mock(post.card_manager)

    # handle delete event, check mock calls
    post.on_delete()
    assert len(post.card_manager.mock_calls) == 1
    card_spec1 = post.card_manager.mock_calls[0].args[0]
    assert card_spec1.card_id == CommentCardSpec(post.user_id, post.id).card_id
    assert post.card_manager.mock_calls == [
        call.remove_card_by_spec_if_exists(card_spec1),
    ]
