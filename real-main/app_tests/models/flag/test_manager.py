import logging
import random
import string

import pytest

from app.models.flag import exceptions


@pytest.fixture
def user(user_manager):
    yield user_manager.create_cognito_only_user('uid1', 'uname1')


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user.id, 'pid1', text='t')


@pytest.fixture
def user2(user_manager):
    yield user_manager.create_cognito_only_user('uid2', 'uname2')


@pytest.fixture
def post2(post_manager, user2):
    yield post_manager.add_post(user2.id, 'pid2', text='t')


def test_flag_post_blocked(flag_manager, block_manager, user, post, user2):
    # post owner blocks user2, verify user2 cannot flag their posts
    block_manager.block(user, user2)
    with pytest.raises(exceptions.FlagException):
        flag_manager.flag_post(user2.id, post)


def test_flag_post_blocker(flag_manager, block_manager, user, post, user2):
    # user2 blocks post owner, verify user2 cannot flag their posts
    block_manager.block(user2, user)
    with pytest.raises(exceptions.FlagException):
        flag_manager.flag_post(user2.id, post)


def test_flag_post_private_not_following(flag_manager, follow_manager, user, post, user2):
    # post owner goes private
    user.set_privacy_status(user.enums.UserPrivacyStatus.PRIVATE)

    # verify user2 cannot flag their posts
    with pytest.raises(exceptions.FlagException):
        flag_manager.flag_post(user2.id, post)

    # user2 follows
    follow_manager.request_to_follow(user2, user)
    follow_manager.accept_follow_request(user2.id, user.id)

    # verify user2 can now flag their posts
    flag_manager.flag_post(user2.id, post)
    assert flag_manager.dynamo.get_flag(post.id, user2.id) is not None


def test_flag(flag_manager, post, user2):
    # verify the flag count
    assert post.item.get('flagCount', 0) == 0

    # flag the post
    post = flag_manager.flag_post(user2.id, post)
    assert post.item.get('flagCount', 0) == 1

    # check that really got to the DB
    post.refresh_item()
    assert post.item.get('flagCount', 0) == 1

    # verify we can't re-flag
    with pytest.raises(exceptions.AlreadyFlagged):
        flag_manager.flag_post(user2.id, post)


def test_flag_threshold_met(flag_manager, caplog, post):
    # verify the flag count
    assert post.item.get('flagCount', 0) == 0

    # add enough flags until the threshold is met
    with caplog.at_level(logging.WARNING):
        for _ in range(flag_manager.flagged_alert_threshold):
            random_user_id = ''.join(random.choices(string.ascii_lowercase, k=10))
            flag_manager.flag_post(random_user_id, post)

    # verify an error was logged
    assert 'FLAGGED' in caplog.text
    assert post.id in caplog.text


def test_unflag_post(flag_manager, user, post, user2):
    # flag the post
    flag_manager.flag_post(user2.id, post)
    assert flag_manager.dynamo.get_flag(post.id, user2.id) is not None

    # check post count
    post.refresh_item()
    assert post.item.get('flagCount', 0) == 1

    # unflag the post
    flag_manager.unflag_post(user2.id, post.id)
    assert flag_manager.dynamo.get_flag(post.id, user2.id) is None

    # check post count
    post.refresh_item()
    assert post.item.get('flagCount', 0) == 0


def test_unflag_post_not_flagged(flag_manager, post, user2):
    # verify can't unflag post that hasn't been flaged
    # note that moto raises the wrong error here because the first transaction
    # succedes, when it should fail
    with pytest.raises(exceptions.NotFlagged):
        flag_manager.unflag_post(user2.id, post.id)


def test_unflag_post_that_doesnt_exist(flag_manager, post, user2):
    # verify can't unflag post that doesn't exist
    # moto raises the wrong error here
    with pytest.raises(exceptions.NotFlagged):
        flag_manager.unflag_post(user2.id, 'pid-dne')


def test_unflag_all_by_user(flag_manager, user, post, post2):
    # check no error unflagging when user hasn't flagged anything
    flag_manager.unflag_all_by_user(user.id)

    # user flags both posts
    flag_manager.flag_post(user.id, post)
    flag_manager.flag_post(user.id, post2)

    # check we see the flags
    len(list(flag_manager.dynamo.generate_flag_items_by_user(user.id))) == 2

    # unflag all the user's flags
    flag_manager.unflag_all_by_user(user.id)

    # check the flags have disappeared
    assert list(flag_manager.dynamo.generate_flag_items_by_user(user.id)) == []


def test_unflag_all_on_post(flag_manager, user, post, user2):
    # check no error unflagging when there are no flags on post
    flag_manager.unflag_all_on_post(post.id)

    # both users flag the post
    flag_manager.flag_post(user.id, post)
    flag_manager.flag_post(user2.id, post)

    # check we see the flags
    len(list(flag_manager.dynamo.generate_flag_items_by_post(post.id))) == 2

    # unflag all the user's flags
    flag_manager.unflag_all_on_post(post.id)

    # check the flags have disappeared
    assert list(flag_manager.dynamo.generate_flag_items_by_post(post.id)) == []
