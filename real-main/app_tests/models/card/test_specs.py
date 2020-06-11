from uuid import uuid4

import pytest

from app.models.card import specs
from app.models.card.exceptions import MalformedCardId
from app.models.post.enums import PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def post(user, post_manager):
    yield post_manager.add_post(user, str(uuid4()), PostType.TEXT_ONLY, text='go go')


post1 = post
post2 = post


def test_comment_card_spec(user, post):
    spec = specs.CommentCardSpec(user.id, post.id)
    assert spec.title == 'You have new comments'
    assert spec.user_id == user.id
    assert spec.post_id == post.id
    assert user.id in spec.card_id
    assert post.id in spec.card_id
    assert 'https://real.app/chat/' in spec.action
    assert post.id in spec.action


def test_comment_card_specs_are_per_post(user, post1, post2):
    assert specs.CommentCardSpec(user.id, post1.id) == specs.CommentCardSpec(user.id, post1.id)
    assert specs.CommentCardSpec(user.id, post1.id) != specs.CommentCardSpec(user.id, post2.id)


def test_chat_card_spec(user):
    spec = specs.ChatCardSpec(user.id)
    assert spec.title == 'You have new messages'
    assert spec.user_id == user.id
    assert user.id in spec.card_id
    assert spec.action == 'https://real.app/chat/'


def test_from_card_id():
    # unrecognized card id formats
    assert specs.CardSpec.from_card_id(None) is None
    assert specs.CardSpec.from_card_id('unrecognized') is None

    # mal-formed card id formats
    with pytest.raises(MalformedCardId):
        specs.CardSpec.from_card_id('malformed-no-post-id:COMMENT_ACTIVITY')
    with pytest.raises(MalformedCardId):
        specs.CardSpec.from_card_id('CHAT_ACTIVITY')

    # well-formed comment activity card id
    user_id, post_id = f'us-east-1:{uuid4()}', str(uuid4())
    spec = specs.CardSpec.from_card_id(f'{user_id}:COMMENT_ACTIVITY:{post_id}')
    assert isinstance(spec, specs.CommentCardSpec)
    assert spec.user_id == user_id
    assert spec.post_id == post_id

    # well-formed chat activity card id
    user_id = f'us-east-1:{uuid4()}'
    spec = specs.CardSpec.from_card_id(f'{user_id}:CHAT_ACTIVITY')
    assert isinstance(spec, specs.ChatCardSpec)
    assert spec.user_id == user_id
