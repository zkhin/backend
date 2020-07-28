import random
from unittest.mock import call, patch
from uuid import uuid4

import pytest

from app.models.card import specs
from app.models.card.enums import CardNotificationType
from app.models.post.enums import PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def chat_card_spec(card_manager, user):
    spec = specs.ChatCardSpec(user.id, chats_with_unviewed_messages_count=2)
    card_manager.add_or_update_card_by_spec(spec)
    yield spec


@pytest.fixture
def requested_followers_card_spec(card_manager, user):
    spec = specs.RequestedFollowersCardSpec(user.id, requested_followers_count=3)
    card_manager.add_or_update_card_by_spec(spec)
    yield spec


@pytest.fixture
def card(user, card_manager):
    yield card_manager.add_card(user.id, 'card title', 'https://action')


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user, str(uuid4()), PostType.TEXT_ONLY, text='go go')


@pytest.fixture
def comment_card_spec(card_manager, post):
    spec = specs.CommentCardSpec(post.user_id, post.id, unviewed_comments_count=42)
    card_manager.add_or_update_card_by_spec(spec)
    yield spec


@pytest.fixture
def post_likes_card_spec(card_manager, post):
    spec = specs.PostLikesCardSpec(post.user_id, post.id)
    with patch.object(spec, 'only_usernames', []):
        card_manager.add_or_update_card_by_spec(spec)
    yield spec


@pytest.fixture
def post_views_card_spec(card_manager, post):
    spec = specs.PostViewsCardSpec(post.user_id, post.id)
    with patch.object(spec, 'only_usernames', []):
        card_manager.add_or_update_card_by_spec(spec)
    yield spec


@pytest.mark.parametrize(
    'spec',
    pytest.lazy_fixture(
        [
            'chat_card_spec',
            'requested_followers_card_spec',
            'comment_card_spec',
            'post_likes_card_spec',
            'post_views_card_spec',
        ]
    ),
)
def test_on_user_delete_delete_cards(card_manager, user, spec):
    # verify starting state
    assert card_manager.get_card(spec.card_id)

    # trigger, verify deletes card
    card_manager.on_user_delete_delete_cards(user.id, old_item=user.item)
    assert card_manager.get_card(spec.card_id) is None

    # trigger, verify no error if there are no cards to delete
    card_manager.on_user_delete_delete_cards(user.id, user.item)
    assert card_manager.get_card(spec.card_id) is None


@pytest.mark.parametrize(
    'spec', pytest.lazy_fixture(['comment_card_spec', 'post_likes_card_spec', 'post_views_card_spec']),
)
def test_on_post_delete_delete_cards(card_manager, post, spec):
    # verify starting state
    assert card_manager.get_card(spec.card_id)

    # trigger, verify deletes card
    card_manager.on_post_delete_delete_cards(post.id, old_item=post.item)
    assert card_manager.get_card(spec.card_id) is None

    # trigger, verify no error if there are no cards to delete
    card_manager.on_post_delete_delete_cards(post.id, post.item)
    assert card_manager.get_card(spec.card_id) is None


@pytest.mark.parametrize(
    'spec', pytest.lazy_fixture(['comment_card_spec', 'post_likes_card_spec', 'post_views_card_spec']),
)
def test_on_post_view_count_change_updates_cards(card_manager, post, spec):
    # verify starting state
    assert card_manager.get_card(spec.card_id)

    # react to a view by a non-post owner, verify doesn't change state
    new_item = old_item = {'sortKey': f'view/{uuid4()}'}
    card_manager.on_post_view_count_change_update_cards(post.id, new_item=new_item, old_item=old_item)
    assert card_manager.get_card(spec.card_id)

    # react to the viewCount going down by post owner, verify doesn't change state
    new_item = {'sortKey': f'view/{post.user_id}', 'viewCount': 2}
    old_item = {'sortKey': f'view/{post.user_id}', 'viewCount': 3}
    card_manager.on_post_view_count_change_update_cards(post.id, new_item=new_item, old_item=old_item)
    assert card_manager.get_card(spec.card_id)

    # react to a view by post owner, verify card deleted
    new_item = {'sortKey': f'view/{post.user_id}', 'viewCount': 3}
    old_item = {'sortKey': f'view/{post.user_id}', 'viewCount': 2}
    card_manager.on_post_view_count_change_update_cards(post.id, new_item=new_item, old_item=old_item)
    assert card_manager.get_card(spec.card_id) is None


def test_on_card_add_sends_gql_notification(card_manager, card, user):
    with patch.object(card_manager, 'appsync') as appsync_mock:
        card_manager.on_card_add(card.id, card.item)
    assert appsync_mock.mock_calls == [
        call.trigger_notification(
            CardNotificationType.ADDED,
            user.id,
            card.id,
            card.item['title'],
            card.item['action'],
            sub_title=card.item.get('subTitle'),
        )
    ]


def test_on_card_edit_sends_gql_notification(card_manager, card, user):
    with patch.object(card_manager, 'appsync') as appsync_mock:
        card_manager.on_card_edit(card.id, old_item={'unused': True}, new_item=card.item)
    assert appsync_mock.mock_calls == [
        call.trigger_notification(
            CardNotificationType.EDITED,
            user.id,
            card.id,
            card.item['title'],
            card.item['action'],
            sub_title=card.item.get('subTitle'),
        )
    ]


def test_on_card_delete_sends_gql_notification(card_manager, card, user):
    with patch.object(card_manager, 'appsync') as appsync_mock:
        card_manager.on_card_delete(card.id, card.item)
    assert appsync_mock.mock_calls == [
        call.trigger_notification(
            CardNotificationType.DELETED,
            user.id,
            card.id,
            card.item['title'],
            card.item['action'],
            sub_title=card.item.get('subTitle'),
        )
    ]


@pytest.mark.parametrize(
    'method_name, card_spec_class, dynamo_attribute',
    [
        [
            'on_user_followers_requested_count_change_sync_card',
            specs.RequestedFollowersCardSpec,
            'followersRequestedCount',
        ],
        [
            'on_user_chats_with_unviewed_messages_count_change_sync_card',
            specs.ChatCardSpec,
            'chatsWithUnviewedMessagesCount',
        ],
    ],
)
def test_on_user_count_change_sync_card(card_manager, user, method_name, card_spec_class, dynamo_attribute):
    card_id = card_spec_class(user.id).card_id
    assert user.item.get(dynamo_attribute) is None

    # refresh with None
    with patch.object(card_manager, 'remove_card_by_spec_if_exists') as remove_mock:
        with patch.object(card_manager, 'add_or_update_card_by_spec') as add_update_mock:
            getattr(card_manager, method_name)(user.id, user.item, user.item)
    assert add_update_mock.call_count == 0
    card_spec = remove_mock.call_args.args[0]
    assert card_spec.card_id == card_id
    assert remove_mock.call_args_list == [call(card_spec)]

    # refresh with zero
    user.item[dynamo_attribute] = 0
    with patch.object(card_manager, 'remove_card_by_spec_if_exists') as remove_mock:
        with patch.object(card_manager, 'add_or_update_card_by_spec') as add_update_mock:
            getattr(card_manager, method_name)(user.id, user.item, user.item)
    assert add_update_mock.call_count == 0
    card_spec = remove_mock.call_args.args[0]
    assert card_spec.card_id == card_id
    assert remove_mock.call_args_list == [call(card_spec)]

    # refresh with one
    user.item[dynamo_attribute] = 1
    with patch.object(card_manager, 'remove_card_by_spec_if_exists') as remove_mock:
        with patch.object(card_manager, 'add_or_update_card_by_spec') as add_update_mock:
            getattr(card_manager, method_name)(user.id, user.item, user.item)
    assert remove_mock.call_count == 0
    card_spec = add_update_mock.call_args.args[0]
    assert card_spec.card_id == card_id
    assert ' 1 ' in card_spec.title
    assert add_update_mock.call_args_list == [call(card_spec)]

    # refresh with two
    user.item[dynamo_attribute] = 2
    with patch.object(card_manager, 'remove_card_by_spec_if_exists') as remove_mock:
        with patch.object(card_manager, 'add_or_update_card_by_spec') as add_update_mock:
            getattr(card_manager, method_name)(user.id, user.item, user.item)
    assert remove_mock.call_count == 0
    card_spec = add_update_mock.call_args.args[0]
    assert card_spec.card_id == card_id
    assert ' 2 ' in card_spec.title
    assert add_update_mock.call_args_list == [call(card_spec)]


def test_on_post_comments_unviewed_count_change_update_card(card_manager, post):
    # check starting state
    assert 'commentsUnviewedCount' not in post.item
    spec = specs.CommentCardSpec(post.user_id, post.id)
    assert card_manager.get_card(spec.card_id) is None

    # add an unviewed comment, check state
    old_item = post.item.copy()
    post.item['commentsUnviewedCount'] = 1
    card_manager.on_post_comments_unviewed_count_change_update_card(
        post.id, new_item=post.item, old_item=old_item
    )
    assert ' 1 ' in card_manager.get_card(spec.card_id).title

    # add another unviewed comment, check state
    old_item = post.item.copy()
    post.item['commentsUnviewedCount'] = 2
    card_manager.on_post_comments_unviewed_count_change_update_card(
        post.id, new_item=post.item, old_item=old_item
    )
    assert ' 2 ' in card_manager.get_card(spec.card_id).title

    # jump down to no unviewed comments, check calls
    old_item = post.item.copy()
    post.item['commentsUnviewedCount'] = 0
    card_manager.on_post_comments_unviewed_count_change_update_card(
        post.id, new_item=post.item, old_item=old_item
    )
    assert card_manager.get_card(spec.card_id) is None


def test_on_post_likes_count_change_update_card(card_manager, post, user):
    # configure and check starting state
    assert 'onymousLikeCount' not in post.item
    assert 'anonymousLikeCount' not in post.item
    spec = specs.PostLikesCardSpec(post.user_id, post.id)
    assert card_manager.get_card(spec.card_id) is None
    if spec.only_usernames:
        user.dynamo.update_user_username(user.id, random.choice(spec.only_usernames), user.username)

    # record a like, verify card is created
    old_item = post.item.copy()
    post.item['anonymousLikeCount'] = 2
    card_manager.on_post_likes_count_change_update_card(post.id, new_item=post.item, old_item=old_item)
    assert card_manager.get_card(spec.card_id)

    # delete the card
    card_manager.remove_card_by_spec_if_exists(spec)
    assert card_manager.get_card(spec.card_id) is None

    # record nine likes, verify card is created
    old_item = post.item.copy()
    post.item['onymousLikeCount'] = 7
    card_manager.on_post_likes_count_change_update_card(post.id, new_item=post.item, old_item=old_item)
    assert card_manager.get_card(spec.card_id)

    # delete the card
    card_manager.remove_card_by_spec_if_exists(spec)
    assert card_manager.get_card(spec.card_id) is None

    # record a 10th like, verify card is **not** created
    old_item = post.item.copy()
    post.item['anonymousLikeCount'] = 3
    card_manager.on_post_likes_count_change_update_card(post.id, new_item=post.item, old_item=old_item)
    assert card_manager.get_card(spec.card_id) is None


def test_on_post_viewed_by_count_change_update_card(card_manager, post, user):
    # check starting state
    assert 'viewedByCount' not in post.item
    spec = specs.PostViewsCardSpec(post.user_id, post.id)
    assert card_manager.get_card(spec.card_id) is None
    if spec.only_usernames:
        user.dynamo.update_user_username(user.id, random.choice(spec.only_usernames), user.username)

    # jump up to five views, process, check no card created
    old_item = post.item.copy()
    post.item['viewedByCount'] = 5
    card_manager.on_post_viewed_by_count_change_update_card(post.id, new_item=post.item, old_item=old_item)
    assert card_manager.get_card(spec.card_id) is None

    # go to six views, process, check card created
    old_item = post.item.copy()
    post.item['viewedByCount'] = 6
    card_manager.on_post_viewed_by_count_change_update_card(post.id, new_item=post.item, old_item=old_item)
    assert card_manager.get_card(spec.card_id)

    # delete the card
    card_manager.remove_card_by_spec_if_exists(spec)
    assert card_manager.get_card(spec.card_id) is None

    # jump up to seven views, process, check no card created
    old_item = post.item.copy()
    post.item['viewedByCount'] = 7
    card_manager.on_post_viewed_by_count_change_update_card(post.id, new_item=post.item, old_item=old_item)
    assert card_manager.get_card(spec.card_id) is None
