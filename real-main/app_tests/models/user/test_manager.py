import re
import uuid
from decimal import Decimal
from unittest import mock

import pendulum
import pytest

from app.utils import GqlNotificationType


@pytest.fixture
def cognito_only_user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_user_pool_entry(user_id, username, verified_email=f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user1 = cognito_only_user
user2 = cognito_only_user
user3 = cognito_only_user


@pytest.fixture
def real_user(user_manager, cognito_client):
    user_id = str(uuid.uuid4())
    cognito_client.create_user_pool_entry(user_id, 'real', verified_email='real-test@real.app')
    yield user_manager.create_cognito_only_user(user_id, 'real')


def test_get_user_that_doesnt_exist(user_manager):
    resp = user_manager.get_user('nope-not-there')
    assert resp is None


def test_get_user_by_username(user_manager, user1):
    # check a user that doesn't exist
    user = user_manager.get_user_by_username('nope_not_there')
    assert user is None

    # check a user that exists
    user = user_manager.get_user_by_username(user1.username)
    assert user.id == user1.id


def test_generate_username(user_manager):
    for _ in range(10):
        username = user_manager.generate_username()
        user_manager.validate_username(username)  # should not raise exception


def test_follow_real_user_exists(user_manager, user1, follower_manager, real_user):
    # verify no followers (ensures user1 fixture generated before real_user)
    assert list(follower_manager.dynamo.generate_followed_items(user1.id)) == []

    # follow that real user
    user_manager.follow_real_user(user1)
    followeds = list(follower_manager.dynamo.generate_followed_items(user1.id))
    assert len(followeds) == 1
    assert followeds[0]['followedUserId'] == real_user.id


def test_follow_real_user_doesnt_exist(user_manager, user1, follower_manager):
    assert list(follower_manager.dynamo.generate_followed_items(user1.id)) == []
    user_manager.follow_real_user(user1)
    assert list(follower_manager.dynamo.generate_followed_items(user1.id)) == []


def test_get_available_placeholder_photo_codes(user_manager):
    s3_client = user_manager.s3_placeholder_photos_client
    user_manager.placeholder_photos_directory = 'placeholder-photos'

    # check before we add any placeholder photos
    codes = user_manager.get_available_placeholder_photo_codes()
    assert codes == []

    # add a placeholder photo, check again
    path = 'placeholder-photos/black-white-cat/native.jpg'
    s3_client.put_object(path, b'placeholder', 'image/jpeg')
    codes = user_manager.get_available_placeholder_photo_codes()
    assert len(codes) == 1
    assert codes[0] == 'black-white-cat'

    # add another placeholder photo, check again
    path = 'placeholder-photos/orange-person/native.jpg'
    s3_client.put_object(path, b'placeholder', 'image/jpeg')
    path = 'placeholder-photos/orange-person/4k.jpg'
    s3_client.put_object(path, b'placeholder', 'image/jpeg')
    codes = user_manager.get_available_placeholder_photo_codes()
    assert len(codes) == 2
    assert codes[0] == 'black-white-cat'
    assert codes[1] == 'orange-person'


def test_get_random_placeholder_photo_code(user_manager):
    s3_client = user_manager.s3_placeholder_photos_client
    user_manager.placeholder_photos_directory = 'placeholder-photos'

    # check before we add any placeholder photos
    code = user_manager.get_random_placeholder_photo_code()
    assert code is None

    # add a placeholder photo, check again
    path = 'placeholder-photos/black-white-cat/native.jpg'
    s3_client.put_object(path, b'placeholder', 'image/jpeg')
    code = user_manager.get_random_placeholder_photo_code()
    assert code == 'black-white-cat'

    # add another placeholder photo, check again
    path = 'placeholder-photos/orange-person/native.jpg'
    s3_client.put_object(path, b'placeholder', 'image/jpeg')
    path = 'placeholder-photos/orange-person/4k.jpg'
    s3_client.put_object(path, b'placeholder', 'image/jpeg')
    code = user_manager.get_random_placeholder_photo_code()
    assert code in ['black-white-cat', 'orange-person']


def test_get_text_tags(user_manager, user1, user2):
    # no tags
    text = 'no tags here'
    assert user_manager.get_text_tags(text) == []

    # with tags, but not of users that exist
    text = 'hey @youDontExist and @meneither'
    assert user_manager.get_text_tags(text) == []

    # with tags, some that exist and others that dont
    text = f'hey @{user1.username} and @nopenope and @{user2.username}'
    assert sorted(user_manager.get_text_tags(text), key=lambda x: x['tag']) == sorted(
        [{'tag': f'@{user1.username}', 'userId': user1.id}, {'tag': f'@{user2.username}', 'userId': user2.id}],
        key=lambda x: x['tag'],
    )


def test_username_tag_regex(user_manager):
    reg = user_manager.username_tag_regex

    # no tags
    assert re.findall(reg, '') == []
    assert re.findall(reg, 'no tags here') == []

    # basic tags
    assert re.findall(reg, 'hi @you how @are @you') == ['@you', '@are', '@you']
    assert re.findall(reg, 'hi @y3o@m.e@ever_yone') == ['@y3o', '@m.e', '@ever_yone']

    # near misses
    assert re.findall(reg, 'too @34 @.. @go!forit @no-no') == []

    # uglies
    assert re.findall(reg, 'hi @._._ @4_. @A_A\n@B.4\r@333!?') == ['@._._', '@4_.', '@A_A', '@B.4', '@333']


def test_clear_expired_subscriptions(user_manager, user1, user2, user3):
    sub_duration = pendulum.duration(months=3)
    ms = pendulum.duration(microseconds=1)

    # grant these users subscriptions that expire at different times, verify
    now1 = pendulum.now('utc')
    user1.grant_subscription_bonus(now=now1)
    user2.grant_subscription_bonus(now=now1 + pendulum.duration(hours=1))
    user3.grant_subscription_bonus(now=now1 + pendulum.duration(hours=2))
    assert user1.refresh_item().item['subscriptionLevel']
    assert user2.refresh_item().item['subscriptionLevel']
    assert user3.refresh_item().item['subscriptionLevel']

    # test clear none
    assert user_manager.clear_expired_subscriptions() == 0
    assert user_manager.clear_expired_subscriptions(now=now1 + sub_duration - ms) == 0
    assert user1.refresh_item().item['subscriptionLevel']
    assert user2.refresh_item().item['subscriptionLevel']
    assert user3.refresh_item().item['subscriptionLevel']

    # test clear one of them
    assert user_manager.clear_expired_subscriptions(now=now1 + sub_duration) == 1
    assert 'subscriptionLevel' not in user1.refresh_item().item
    assert user2.refresh_item().item['subscriptionLevel']
    assert user3.refresh_item().item['subscriptionLevel']

    # test clear two of them
    assert user_manager.clear_expired_subscriptions(now=now1 + sub_duration + pendulum.duration(hours=2)) == 2
    assert 'subscriptionLevel' not in user1.refresh_item().item
    assert 'subscriptionLevel' not in user2.refresh_item().item
    assert 'subscriptionLevel' not in user3.refresh_item().item


def test_fire_gql_subscription_chats_with_unviewed_messages_count(user_manager):
    user_id = str(uuid.uuid4())
    user_item = {'chatsWithUnviewedMessagesCount': Decimal(34), 'otherField': 'anything'}
    with mock.patch.object(user_manager, 'appsync_client') as appsync_client_mock:
        user_manager.fire_gql_subscription_chats_with_unviewed_messages_count(user_id, user_item, 'unused')
    assert appsync_client_mock.mock_calls == [
        mock.call.fire_notification(
            user_id,
            GqlNotificationType.USER_CHATS_WITH_UNVIEWED_MESSAGES_COUNT_CHANGED,
            userChatsWithUnviewedMessagesCount=34,
        )
    ]
    # Decimals cause problems when serializing to JSON so make sure we've converted to int
    assert isinstance(
        appsync_client_mock.fire_notification.call_args.kwargs['userChatsWithUnviewedMessagesCount'], int
    )
