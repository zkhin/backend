import logging
import uuid

import pendulum
import pytest

from app.models.post.enums import PostType
from app.models.user.enums import UserSubscriptionLevel


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_user_pool_entry(user_id, username, verified_email=f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user
user3 = user


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user, str(uuid.uuid4()), PostType.TEXT_ONLY, text='t')


post2 = post


def test_record_view_count_logs_warning_for_non_completed_posts(post, user2, caplog):
    # verify no warning for a completed post
    with caplog.at_level(logging.WARNING):
        post.record_view_count(user2.id, 2)
    assert len(caplog.records) == 0

    # verify warning for a non-completed post
    post.archive()
    with caplog.at_level(logging.WARNING):
        post.record_view_count(user2.id, 2)
    assert len(caplog.records) == 1
    assert user2.id in caplog.records[0].msg
    assert post.id in caplog.records[0].msg


def test_record_view_count_records_to_original_post_as_well(post, post2, user2):
    # verify post owner's view doesn't make it up to the original
    post.item['originalPostId'] = post2.id
    post.record_view_count(post.user_id, 1)
    assert post.view_dynamo.get_view(post.id, post.user_id)
    assert post2.view_dynamo.get_view(post2.id, post.user_id) is None

    # verify a rando's view is recorded locally and goes up to the orginal
    assert post.view_dynamo.get_view(post.id, user2.id) is None
    assert post2.view_dynamo.get_view(post2.id, user2.id) is None
    post.item['originalPostId'] = post2.id
    post.record_view_count(user2.id, 1)
    assert post.view_dynamo.get_view(post.id, user2.id)
    assert post2.view_dynamo.get_view(post2.id, user2.id)


def test_text_only_posts_trend(post_manager, user, user2):
    now = pendulum.parse('2020-06-09T00:00:00Z')  # exact begining of day so post gets exactly one free trending
    post = post_manager.add_post(user, str(uuid.uuid4()), PostType.TEXT_ONLY, text='t', now=now)
    assert post.type == PostType.TEXT_ONLY
    assert post.trending_score == 1
    assert user.trending_score is None

    # record a view, verify that boosts trending score
    viewed_at = pendulum.parse('2020-06-10T00:00:00Z')  # exactly one day forward
    post.record_view_count(user2.id, 4, viewed_at=viewed_at)
    assert post.trending_score == 1 + 2
    assert post.refresh_trending_item().trending_score == 1 + 2
    assert user.refresh_trending_item()
    assert pendulum.parse(user.trending_item['lastDeflatedAt']) == viewed_at
    assert user.trending_score == 1


def test_only_first_view_of_post_causes_trending(post_manager, user, user2, user3):
    # add a post
    post = post_manager.add_post(user, str(uuid.uuid4()), PostType.TEXT_ONLY, text='t')
    assert post.type == PostType.TEXT_ONLY
    assert post.trending_score is not None
    assert user.trending_score is None

    # record a view, verify that boosts trending score
    org_post_trending_score = post.trending_score
    post.record_view_count(user2.id, 4)
    assert post.refresh_trending_item().trending_score > org_post_trending_score
    assert user.refresh_trending_item().trending_score is not None

    # record another view by the same user, verify trending scores don't change
    org_post_trending_score = post.trending_score
    org_user_trending_score = post.user.trending_score
    post.record_view_count(user2.id, 2)
    assert post.refresh_trending_item().trending_score == org_post_trending_score
    assert user.refresh_trending_item().trending_score == org_user_trending_score

    # record a view by a different user, verify trending scores go up again
    org_post_trending_score = post.trending_score
    org_user_trending_score = post.user.trending_score
    post.record_view_count(user3.id, 2)
    assert post.refresh_trending_item().trending_score > org_post_trending_score
    assert user.refresh_trending_item().trending_score > org_user_trending_score


def test_non_verified_image_posts_trend_with_lower_multiplier(post_manager, user, user2, image_data_b64):
    # create an original post that fails verification
    now = pendulum.parse('2020-06-09T00:00:00Z')  # exact begining of day so post gets exactly one free trending
    post_manager.clients['post_verification'].configure_mock(**{'verify_image.return_value': False})
    post = post_manager.add_post(
        user,
        str(uuid.uuid4()),
        PostType.IMAGE,
        image_input={'imageData': image_data_b64},
        now=now,
    )
    assert post.type == PostType.IMAGE
    assert post.is_verified is False
    assert post.original_post_id == post.id
    assert post.trending_score == 0.5
    assert post.refresh_trending_item().trending_score == 0.5
    assert user.refresh_trending_item().trending_score is None  # users don't get a free boost into trending

    # record a view, verify adds to trending
    viewed_at = pendulum.parse('2020-06-10T00:00:00Z')  # exactly one day forward
    post.record_view_count(user2.id, 4, viewed_at=viewed_at)
    assert post.trending_score == 0.5 + 1
    assert post.refresh_trending_item().trending_score == 0.5 + 1
    assert user.refresh_trending_item().trending_score == 0.5  # includes an extra deflation compared to post


def test_text_only_posts_trend_with_full_multiplier(post_manager, user, user2):
    # create an original post that fails verification
    now = pendulum.parse('2020-06-09T00:00:00Z')  # exact begining of day so post gets exactly one free trending
    post = post_manager.add_post(user, str(uuid.uuid4()), PostType.TEXT_ONLY, text='lore ipsum', now=now)
    assert post.type == PostType.TEXT_ONLY
    assert post.is_verified is None
    assert post.original_post_id == post.id
    assert post.trending_score == 1
    assert post.refresh_trending_item().trending_score == 1
    assert user.refresh_trending_item().trending_score is None  # users don't get a free boost into trending

    # record a view, verify adds to trending
    viewed_at = pendulum.parse('2020-06-10T00:00:00Z')  # exactly one day forward
    post.record_view_count(user2.id, 4, viewed_at=viewed_at)
    assert post.trending_score == 2 + 1
    assert post.refresh_trending_item().trending_score == 2 + 1
    assert user.refresh_trending_item().trending_score == 1  # includes an extra deflation compared to post


def test_posts_from_subscriber_trend_with_boosted_multiplier(post_manager, user, user2):
    # create an original post that fails verification
    assert user.grant_subscription_bonus().subscription_level == UserSubscriptionLevel.DIAMOND
    now = pendulum.parse('2020-06-09T00:00:00Z')  # exact begining of day so post gets exactly one free trending
    post = post_manager.add_post(user, str(uuid.uuid4()), PostType.TEXT_ONLY, text='lore ipsum', now=now)
    assert post.type == PostType.TEXT_ONLY
    assert post.is_verified is None
    assert post.original_post_id == post.id
    assert post.trending_score == 4
    assert post.refresh_trending_item().trending_score == 4
    assert user.refresh_trending_item().trending_score is None  # users don't get a free boost into trending

    # record a view, verify adds to trending
    viewed_at = pendulum.parse('2020-06-10T00:00:00Z')  # exactly one day forward
    post.record_view_count(user2.id, 4, viewed_at=viewed_at)
    assert post.trending_score == 8 + 4
    assert post.refresh_trending_item().trending_score == 8 + 4
    assert user.refresh_trending_item().trending_score == 4  # includes an extra deflation compared to post


def test_verified_image_posts_originality_determines_trending(post_manager, user, image_data_b64, user2, user3):
    # create an original image post
    now = pendulum.parse('2020-06-09T00:00:00Z')  # exact begining of day so post gets exactly one free trending
    post = post_manager.add_post(
        user, str(uuid.uuid4()), PostType.IMAGE, image_input={'imageData': image_data_b64}, now=now
    )
    assert post.type == PostType.IMAGE
    assert post.is_verified is True
    assert post.original_post_id == post.id
    assert post.trending_score == 1
    assert post.refresh_trending_item().trending_score == 1
    assert user.refresh_trending_item().trending_score is None

    # record a view, verify that boosts trending score
    viewed_at = pendulum.parse('2020-06-10T00:00:00Z')  # exactly one day forward
    post.record_view_count(user2.id, 4, viewed_at=viewed_at)
    assert post.trending_score == 1 + 2
    assert post.refresh_trending_item().trending_score == 1 + 2
    assert user.refresh_trending_item()
    assert pendulum.parse(user.trending_item['lastDeflatedAt']) == viewed_at
    assert user.trending_score == 1

    # other user adds a non-orginal copy of the first post
    now = pendulum.parse('2020-06-09T12:00:00Z')
    post2 = post_manager.add_post(
        user2, str(uuid.uuid4()), PostType.IMAGE, image_input={'imageData': image_data_b64}, now=now
    )
    assert post2.type == PostType.IMAGE
    assert post2.is_verified is True
    assert post2.original_post_id == post.id
    assert post2.trending_score is None
    assert post2.refresh_trending_item().trending_score is None
    assert user2.refresh_trending_item().trending_score is None

    # verify no affect on original post, user - yet
    assert post.refresh_trending_item().trending_score == 1 + 2
    assert user.refresh_trending_item().trending_score == 1

    # record a view on that copy by a third user
    viewed_at = pendulum.parse('2020-06-10T00:00:00Z')  # 12 hours forward for original post
    post2.record_view_count(user3.id, 8, viewed_at=viewed_at)
    assert post2.trending_score is None
    assert post2.refresh_trending_item().trending_score is None
    assert user2.refresh_trending_item().trending_score is None

    # verify those trending points went to the original post & user
    assert post.refresh_trending_item().trending_score == 1 + 2 + 2
    assert user.refresh_trending_item().trending_score == 1 + 1


def test_posts_trend_with_view_type(post_manager, user, user2):
    now = pendulum.parse('2020-06-09T00:00:00Z')  # exact begining of day so post gets exactly one free trending
    post = post_manager.add_post(user, str(uuid.uuid4()), PostType.TEXT_ONLY, text='t', now=now)
    assert post.type == PostType.TEXT_ONLY
    assert post.trending_score == 1
    assert user.trending_score is None

    # record a view, verify that boosts trending score
    viewed_at = pendulum.parse('2020-06-10T00:00:00Z')  # exactly one day forward
    post.record_view_count(user2.id, 4, viewed_at=viewed_at, view_type='FOCUS')
    assert post.trending_score == 1 + 4
    assert post.refresh_trending_item().trending_score == 1 + 4
    assert user.refresh_trending_item()
    assert pendulum.parse(user.trending_item['lastDeflatedAt']) == viewed_at
    assert user.trending_score == 2
