from unittest.mock import call, Mock

import pytest

from app.models.like.enums import LikeStatus


@pytest.fixture
def blocker_user(user_manager):
    yield user_manager.create_cognito_only_user('blocker-uid', 'bockerUname')


@pytest.fixture
def blocked_user(user_manager):
    yield user_manager.create_cognito_only_user('blocked-uid', 'bockedUname')


@pytest.fixture
def blocker_user_2(user_manager):
    yield user_manager.create_cognito_only_user('blocker-uid-2', 'bockerUname2')


@pytest.fixture
def blocked_user_2(user_manager):
    yield user_manager.create_cognito_only_user('blocked-uid-2', 'bockedUname2')


def test_block_unfollows(block_manager, follow_manager, blocker_user, blocked_user):
    # mock out calls to the follow manager
    block_manager.follow_manager = Mock(follow_manager)
    block_manager.follow_manager.exceptions = follow_manager.exceptions

    block_item = block_manager.block(blocker_user, blocked_user)
    assert block_item['blockerUserId'] == blocker_user.id
    assert block_item['blockedUserId'] == blocked_user.id

    # check it really is in the DB
    resp = block_manager.dynamo.get_block(blocker_user.id, blocked_user.id)
    assert resp is not None

    # check following manager was called to clear any followings
    assert block_manager.follow_manager.mock_calls == [
        call.unfollow(blocker_user.id, blocked_user.id, force=True),
        call.unfollow(blocked_user.id, blocker_user.id, force=True),
    ]


def test_block_clears_likes(block_manager, blocker_user, blocked_user, post_manager):
    blocker_post_id = 'blocker-post-id'
    blocked_post_id = 'blocked-post-id'

    # we each add a post
    blocker_post = post_manager.add_post(blocker_user.id, blocker_post_id, text='t')
    blocked_post = post_manager.add_post(blocked_user.id, blocked_post_id, text='t')

    # we each like each other's posts
    block_manager.like_manager.like_post(blocker_user, blocked_post, LikeStatus.ONYMOUSLY_LIKED)
    block_manager.like_manager.like_post(blocked_user, blocker_post, LikeStatus.ONYMOUSLY_LIKED)

    # check those likes are really there
    resp = block_manager.like_manager.get_like(blocker_user.id, blocked_post_id)
    assert resp.item['likeStatus'] == LikeStatus.ONYMOUSLY_LIKED
    resp = block_manager.like_manager.get_like(blocked_user.id, blocker_post_id)
    assert resp.item['likeStatus'] == LikeStatus.ONYMOUSLY_LIKED

    # do the blocking
    block_item = block_manager.block(blocker_user, blocked_user)
    assert block_item['blockerUserId'] == blocker_user.id
    assert block_item['blockedUserId'] == blocked_user.id

    # check those likes are no longer there
    assert block_manager.like_manager.get_like(blocker_user.id, blocked_post_id) is None
    assert block_manager.like_manager.get_like(blocked_user.id, blocker_post_id) is None


def test_is_blocked(block_manager, blocker_user, blocked_user):
    # block then unblock, testing block state at every step
    assert block_manager.is_blocked(blocker_user.id, blocked_user.id) is False
    assert block_manager.block(blocker_user, blocked_user)
    assert block_manager.is_blocked(blocker_user.id, blocked_user.id) is True
    assert block_manager.unblock(blocker_user, blocked_user)
    assert block_manager.is_blocked(blocker_user.id, blocked_user.id) is False


def test_get_block_status(block_manager, blocker_user, blocked_user):
    assert block_manager.get_block_status(blocker_user.id, blocker_user.id) == 'SELF'
    assert block_manager.get_block_status(blocker_user.id, blocked_user.id) == 'NOT_BLOCKING'
    assert block_manager.block(blocker_user, blocked_user)
    assert block_manager.get_block_status(blocker_user.id, blocked_user.id) == 'BLOCKING'
    assert block_manager.unblock(blocker_user, blocked_user)
    assert block_manager.get_block_status(blocker_user.id, blocked_user.id) == 'NOT_BLOCKING'


def test_cant_double_block(block_manager, blocker_user, blocked_user):
    block_item = block_manager.block(blocker_user, blocked_user)
    assert block_item['blockerUserId'] == blocker_user.id
    assert block_item['blockedUserId'] == blocked_user.id

    with pytest.raises(block_manager.exceptions.AlreadyBlocked):
        block_manager.block(blocker_user, blocked_user)


def test_unblock(block_manager, blocker_user, blocked_user):
    # do the blocking
    block_item = block_manager.block(blocker_user, blocked_user)
    assert block_item['blockerUserId'] == blocker_user.id
    assert block_item['blockedUserId'] == blocked_user.id

    # unblock
    block_item = block_manager.unblock(blocker_user, blocked_user)
    assert block_item['blockerUserId'] == blocker_user.id
    assert block_item['blockedUserId'] == blocked_user.id

    # check the unblock really did clear the db
    resp = block_manager.dynamo.get_block(blocker_user.id, blocked_user.id)
    assert resp is None


@pytest.mark.xfail(reason='https://github.com/spulec/moto/issues/1071')
def test_cant_unblock_if_not_blocked(block_manager, blocker_user, blocked_user):
    with pytest.raises(block_manager.exceptions.NotBlocked):
        block_manager.unblock(blocker_user, blocked_user)


def test_unblock_all_blocks_by_user(block_manager, blocker_user, blocked_user, blocked_user_2):
    # blocker blocks both the blocked
    block_manager.block(blocker_user, blocked_user)
    block_manager.block(blocker_user, blocked_user_2)

    # check they really are in the DB
    assert block_manager.dynamo.get_block(blocker_user.id, blocked_user.id) is not None
    assert block_manager.dynamo.get_block(blocker_user.id, blocked_user_2.id) is not None

    # clear all our blocks
    block_manager.unblock_all_blocks_by_user(blocker_user.id)

    # check they are no longer in the db
    assert block_manager.dynamo.get_block(blocker_user.id, blocked_user.id) is None
    assert block_manager.dynamo.get_block(blocker_user.id, blocked_user_2.id) is None


def test_unblock_all_blocks_of_user(block_manager, blocker_user, blocker_user_2, blocked_user):
    # blocked gets blocked both the blockers
    block_manager.block(blocker_user, blocked_user)
    block_manager.block(blocker_user_2, blocked_user)

    # check they really are in the DB
    assert block_manager.dynamo.get_block(blocker_user.id, blocked_user.id) is not None
    assert block_manager.dynamo.get_block(blocker_user_2.id, blocked_user.id) is not None

    # clear all our blocks
    block_manager.unblock_all_blocks_of_user(blocked_user.id)

    # check they are no longer in the db
    assert block_manager.dynamo.get_block(blocker_user.id, blocked_user.id) is None
    assert block_manager.dynamo.get_block(blocker_user_2.id, blocked_user.id) is None
