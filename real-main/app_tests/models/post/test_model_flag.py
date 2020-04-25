from unittest.mock import Mock
import uuid

import pytest

from app.models.post.enums import PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id = str(uuid.uuid4())
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username=user_id)
    yield user_manager.create_cognito_only_user(user_id, str(uuid.uuid4())[:8])


user2 = user
user3 = user
user4 = user
user5 = user
user6 = user
user7 = user


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user.id, 'pid1', PostType.TEXT_ONLY, text='t')


def test_flag_success(post, user2):
    # check starting state
    assert post.item.get('flagCount', 0) == 0
    assert len(list(post.flag_dynamo.generate_by_post(post.id))) == 0

    # flag the post, verify
    post.flag(user2)
    assert post.item.get('flagCount', 0) == 1
    assert post.refresh_item().item.get('flagCount', 0) == 1
    assert len(list(post.flag_dynamo.generate_by_post(post.id))) == 1

    # verify we can't flag the post second time
    with pytest.raises(post.exceptions.PostException, match='already been flagged'):
        post.flag(user2)
    assert post.item.get('flagCount', 0) == 1
    assert post.refresh_item().item.get('flagCount', 0) == 1


def test_flag_autoarchive_by_popular_demand(post, user2, user3):
    # test without auto-archiving
    post.should_archive_by_popular_demand = Mock(return_value=False)
    post.flag(user2)
    assert post.status == post.enums.PostStatus.COMPLETED
    assert post.refresh_item().status == post.enums.PostStatus.COMPLETED

    # test with auto-archiving
    post.should_archive_by_popular_demand = Mock(return_value=True)
    post.flag(user3)
    assert post.status == post.enums.PostStatus.ARCHIVED
    assert post.refresh_item().status == post.enums.PostStatus.ARCHIVED


def test_flag_autoarchive_by_admin(post, user2):
    post.flag_admin_usernames = (user2.username,)
    post.flag(user2)
    assert post.status == post.enums.PostStatus.ARCHIVED
    assert post.refresh_item().status == post.enums.PostStatus.ARCHIVED


def test_cant_flag_our_own_post(post, user):
    with pytest.raises(post.exceptions.PostException, match='flag their own'):
        post.flag(user)
    assert post.item.get('flagCount', 0) == 0
    assert post.refresh_item().item.get('flagCount', 0) == 0
    assert list(post.flag_dynamo.generate_by_post(post.id)) == []


def test_cant_flag_post_of_user_thats_blocking_us(post, user, user2, block_manager):
    block_manager.block(user, user2)
    with pytest.raises(post.exceptions.PostException, match='has been blocked by owner'):
        post.flag(user2)
    assert post.item.get('flagCount', 0) == 0
    assert post.refresh_item().item.get('flagCount', 0) == 0
    assert list(post.flag_dynamo.generate_by_post(post.id)) == []


def test_cant_flag_post_of_user_we_are_blocking(post, user, user2, block_manager):
    block_manager.block(user2, user)
    with pytest.raises(post.exceptions.PostException, match='has blocked owner'):
        post.flag(user2)
    assert post.item.get('flagCount', 0) == 0
    assert post.refresh_item().item.get('flagCount', 0) == 0
    assert list(post.flag_dynamo.generate_by_post(post.id)) == []


def test_cant_flag_post_of_private_user_we_are_not_following(post, user, user2, follow_manager):
    # can't flag post of private user we're not following
    user.set_privacy_status(user.enums.UserPrivacyStatus.PRIVATE)
    with pytest.raises(post.exceptions.PostException, match='not have access'):
        post.flag(user2)

    # request to follow - still can't flag
    following = follow_manager.request_to_follow(user2, user)
    with pytest.raises(post.exceptions.PostException, match='not have access'):
        post.flag(user2)

    # deny the follow request - still can't flag
    following.deny()
    with pytest.raises(post.exceptions.PostException, match='not have access'):
        post.flag(user2)

    # check no flags
    assert post.item.get('flagCount', 0) == 0
    assert post.refresh_item().item.get('flagCount', 0) == 0
    assert list(post.flag_dynamo.generate_by_post(post.id)) == []

    # accept the follow request - now can flag
    following.accept()
    post.flag(user2)

    # check the flag exists
    assert post.item.get('flagCount', 0) == 1
    assert post.refresh_item().item.get('flagCount', 0) == 1
    assert len(list(post.flag_dynamo.generate_by_post(post.id))) == 1


def test_unflag(post, user2):
    # flag the post, verify worked
    post.flag(user2)
    assert post.item.get('flagCount', 0) == 1
    assert post.refresh_item().item.get('flagCount', 0) == 1
    assert len(list(post.flag_dynamo.generate_by_post(post.id))) == 1

    # unflag, verify worked
    post.unflag(user2.id)
    assert post.item.get('flagCount', 0) == 0
    assert post.refresh_item().item.get('flagCount', 0) == 0
    assert len(list(post.flag_dynamo.generate_by_post(post.id))) == 0

    # verify can't unflag if we haven't flagged
    with pytest.raises(post.exceptions.PostException, match='not been flagged'):
        post.unflag(user2.id)


def test_should_archive_by_popular_demand(post, user2, user3, user4, user5, user6, user7, view_manager):
    # should archive if over 5 users have viewed the post and more than 10% have flagged it
    # one flag, verify shouldn't auto-archive
    post.flag(user2)
    assert post.should_archive_by_popular_demand() is False

    # get 5 views, verify still shouldn't auto-archive
    view_manager.record_views('post', [post.id], user2.id)
    view_manager.record_views('post', [post.id], user3.id)
    view_manager.record_views('post', [post.id], user4.id)
    view_manager.record_views('post', [post.id], user5.id)
    view_manager.record_views('post', [post.id], user6.id)
    post.refresh_item()
    assert post.should_archive_by_popular_demand() is False

    # get a 6th view, verify should auto-archive now
    view_manager.record_views('post', [post.id], user7.id)
    post.refresh_item()
    assert post.should_archive_by_popular_demand() is True
