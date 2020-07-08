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
    assert not hasattr(spec, 'title')
    assert spec.user_id == user.id
    assert spec.post_id == post.id
    assert user.id in spec.card_id
    assert post.id in spec.card_id
    assert spec.action == f'https://real.app/user/{user.id}/post/{post.id}/comments'
    assert post.id in spec.action


def test_post_views_card_spec(user, post):
    spec = specs.PostViewsCardSpec(user.id, post.id)
    assert spec.user_id == user.id
    assert spec.post_id == post.id
    assert user.id in spec.card_id
    assert post.id in spec.card_id
    assert spec.action == f'https://real.app/user/{user.id}/post/{post.id}/views'
    assert post.id in spec.action
    assert spec.title == 'You have new views'


def test_comment_card_spec_titles(user, post):
    spec = specs.CommentCardSpec(user.id, post.id, unviewed_comments_count=1)
    assert spec.title == 'You have 1 new comment'

    spec = specs.CommentCardSpec(user.id, post.id, unviewed_comments_count=2)
    assert spec.title == 'You have 2 new comments'

    spec = specs.CommentCardSpec(user.id, post.id, unviewed_comments_count=42)
    assert spec.title == 'You have 42 new comments'


def test_comment_card_specs_are_per_post(user, post1, post2):
    assert specs.CommentCardSpec(user.id, post1.id).card_id == specs.CommentCardSpec(user.id, post1.id).card_id
    assert specs.CommentCardSpec(user.id, post1.id).card_id != specs.CommentCardSpec(user.id, post2.id).card_id


def test_chat_card_spec(user):
    spec = specs.ChatCardSpec(user.id)
    assert not hasattr(spec, 'title')
    assert spec.user_id == user.id
    assert user.id in spec.card_id
    assert spec.action == 'https://real.app/chat/'


def test_chat_card_spec_titles(user):
    spec = specs.ChatCardSpec(user.id, chats_with_unviewed_messages_count=1)
    assert spec.title == 'You have 1 chat with new messages'

    spec = specs.ChatCardSpec(user.id, chats_with_unviewed_messages_count=2)
    assert spec.title == 'You have 2 chats with new messages'

    spec = specs.ChatCardSpec(user.id, chats_with_unviewed_messages_count=42)
    assert spec.title == 'You have 42 chats with new messages'


def test_requested_followers_card_spec(user):
    spec = specs.RequestedFollowersCardSpec(user.id)
    assert not hasattr(spec, 'title')
    assert spec.user_id == user.id
    assert user.id in spec.card_id
    assert spec.action == 'https://real.app/chat/'


def test_requested_followers_card_spec_titles(user):
    spec = specs.RequestedFollowersCardSpec(user.id, requested_followers_count=1)
    assert spec.title == 'You have 1 pending follow request'

    spec = specs.RequestedFollowersCardSpec(user.id, requested_followers_count=2)
    assert spec.title == 'You have 2 pending follow requests'

    spec = specs.RequestedFollowersCardSpec(user.id, requested_followers_count=42)
    assert spec.title == 'You have 42 pending follow requests'


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

    # well-formed requested followers card id
    user_id = f'us-east-1:{uuid4()}'
    spec = specs.CardSpec.from_card_id(f'{user_id}:REQUESTED_FOLLOWERS')
    assert isinstance(spec, specs.RequestedFollowersCardSpec)
    assert spec.user_id == user_id
