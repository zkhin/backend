from unittest.mock import Mock, call, patch
from uuid import uuid4

import pendulum
import pytest

from app.models.card.templates import CommentCardTemplate
from app.models.post.enums import PostType
from app.utils import image_size


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def card(user, card_manager):
    yield card_manager.add_card(user.id, 'card title', 'https://action')


@pytest.fixture
def post(user, post_manager):
    yield post_manager.add_post(user, str(uuid4()), PostType.TEXT_ONLY, text='go go')


@pytest.fixture
def comment_card(user, card_manager, post):
    yield card_manager.add_or_update_card_by_template(
        CommentCardTemplate(user.id, post.id, unviewed_comments_count=42)
    )


def test_serialize(user, card):
    # serialize the card without a subtitle
    resp = card.serialize(user.id)
    assert resp['cardId'] == card.id
    assert resp['title'] == card.item['title']
    assert resp['action'] == card.item['action']
    assert 'subTitle' not in card.item

    # add a subtitle, serialize again
    card.item['subTitle'] = 'this is a sub'
    resp = card.serialize(user.id)
    assert resp['cardId'] == card.id
    assert resp['title'] == card.item['title']
    assert resp['action'] == card.item['action']
    assert resp['subTitle'] == card.item['subTitle']


def test_clear_notify_user_at(user, card_manager):
    # create a card with a notify_user_at, verify
    card = card_manager.add_card(user.id, 'title', 'https://action', notify_user_at=pendulum.now('utc'))
    assert card.notify_user_at

    # clear it, verify
    assert card.clear_notify_user_at().notify_user_at is None
    assert card.notify_user_at is None

    # verify idempotent
    assert card.clear_notify_user_at().notify_user_at is None
    assert card.notify_user_at is None


def test_notify_user(user, card):
    mocked_resp = {}
    card.pinpoint_client.configure_mock(**{'send_user_apns.return_value': mocked_resp})
    assert card.pinpoint_client.mock_calls == []
    resp = card.notify_user()
    assert resp is mocked_resp
    assert card.pinpoint_client.mock_calls == [
        call.send_user_apns(user.id, 'https://action', 'card title', body=None)
    ]


def test_delete(card, user):
    assert card.dynamo.get_card(card.id)
    card.delete()
    assert card.dynamo.get_card(card.id) is None


def test_get_image_url(card, post, comment_card):
    assert card.post is None
    assert card.has_thumbnail is False
    assert card.get_image_url(image_size.NATIVE) is None

    assert comment_card.post
    assert comment_card.post.id == post.id
    assert comment_card.has_thumbnail is True

    mocked_url = 'https://' + str(uuid4())
    comment_card._post = Mock(**{'get_image_readonly_url.return_value': mocked_url})
    assert comment_card.get_image_url('whatevs') == mocked_url
    assert comment_card.post.mock_calls == [call.get_image_readonly_url('whatevs')]


def test_trigger_notification(card, user):
    with patch.object(card, 'appsync') as appsync_mock:
        card.trigger_notification('notitype')
    assert appsync_mock.mock_calls == [
        call.trigger_notification(
            'notitype',
            user.id,
            card.id,
            card.item['title'],
            card.item['action'],
            sub_title=card.item.get('subTitle'),
        )
    ]
