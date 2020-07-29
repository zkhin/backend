from uuid import uuid4

import pytest

from app.models.card import templates
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


def test_comment_card_template(user, post):
    template = templates.CommentCardTemplate(user.id, post.id)
    assert not hasattr(template, 'title')
    assert template.user_id == user.id
    assert template.post_id == post.id
    assert user.id in template.card_id
    assert post.id in template.card_id
    assert template.action == f'https://real.app/user/{user.id}/post/{post.id}/comments'
    assert post.id in template.action
    assert not hasattr(template, 'only_usernames')


def test_post_views_card_template(user, post):
    template = templates.PostViewsCardTemplate(user.id, post.id)
    assert template.user_id == user.id
    assert template.post_id == post.id
    assert user.id in template.card_id
    assert post.id in template.card_id
    assert template.action == f'https://real.app/user/{user.id}/post/{post.id}/views'
    assert post.id in template.action
    assert template.title == 'You have new views'
    assert template.only_usernames == ('azim', 'ian', 'mike')


def test_post_likes_card_template(user, post):
    template = templates.PostLikesCardTemplate(user.id, post.id)
    assert template.user_id == user.id
    assert template.post_id == post.id
    assert user.id in template.card_id
    assert post.id in template.card_id
    assert template.action == f'https://real.app/user/{user.id}/post/{post.id}/likes'
    assert post.id in template.action
    assert template.title == 'You have new likes'
    assert template.only_usernames == ('azim', 'ian', 'mike')


def test_comment_card_template_titles(user, post):
    template = templates.CommentCardTemplate(user.id, post.id, unviewed_comments_count=1)
    assert template.title == 'You have 1 new comment'

    template = templates.CommentCardTemplate(user.id, post.id, unviewed_comments_count=2)
    assert template.title == 'You have 2 new comments'

    template = templates.CommentCardTemplate(user.id, post.id, unviewed_comments_count=42)
    assert template.title == 'You have 42 new comments'


def test_comment_card_templates_are_per_post(user, post1, post2):
    assert (
        templates.CommentCardTemplate(user.id, post1.id).card_id
        == templates.CommentCardTemplate(user.id, post1.id).card_id
    )
    assert (
        templates.CommentCardTemplate(user.id, post1.id).card_id
        != templates.CommentCardTemplate(user.id, post2.id).card_id
    )


def test_chat_card_template(user):
    template = templates.ChatCardTemplate(user.id)
    assert not hasattr(template, 'title')
    assert template.user_id == user.id
    assert user.id in template.card_id
    assert template.action == 'https://real.app/chat/'
    assert not hasattr(template, 'only_usernames')


def test_chat_card_template_titles(user):
    template = templates.ChatCardTemplate(user.id, chats_with_unviewed_messages_count=1)
    assert template.title == 'You have 1 chat with new messages'

    template = templates.ChatCardTemplate(user.id, chats_with_unviewed_messages_count=2)
    assert template.title == 'You have 2 chats with new messages'

    template = templates.ChatCardTemplate(user.id, chats_with_unviewed_messages_count=42)
    assert template.title == 'You have 42 chats with new messages'


def test_requested_followers_card_template(user):
    template = templates.RequestedFollowersCardTemplate(user.id)
    assert not hasattr(template, 'title')
    assert template.user_id == user.id
    assert user.id in template.card_id
    assert template.action == 'https://real.app/chat/'
    assert not hasattr(template, 'only_usernames')


def test_requested_followers_card_template_titles(user):
    template = templates.RequestedFollowersCardTemplate(user.id, requested_followers_count=1)
    assert template.title == 'You have 1 pending follow request'

    template = templates.RequestedFollowersCardTemplate(user.id, requested_followers_count=2)
    assert template.title == 'You have 2 pending follow requests'

    template = templates.RequestedFollowersCardTemplate(user.id, requested_followers_count=42)
    assert template.title == 'You have 42 pending follow requests'
