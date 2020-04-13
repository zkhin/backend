import uuid

import pytest

from app.models.like.enums import LikeStatus
from app.models.like.exceptions import NotLikedWithStatus
from app.models.post.enums import PostType
from app.models.post.exceptions import UnableToDecrementPostLikeCounter


@pytest.fixture
def user(user_manager, cognito_client):
    user_id = str(uuid.uuid4())
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username=user_id)
    yield user_manager.create_cognito_only_user(user_id, str(uuid.uuid4())[:8])


other_user = user


@pytest.fixture
def post(dynamo_client, like_manager, user, post_manager):
    yield post_manager.add_post(user.id, 'pid', PostType.TEXT_ONLY, text='lore ipsum')


@pytest.fixture
def like(like_manager, post, user):
    like_manager.like_post(user, post, LikeStatus.ANONYMOUSLY_LIKED)
    yield like_manager.get_like(user.id, post.id)


def test_dislike(like_manager, like):
    liked_by_user_id = like.item['likedByUserId']
    post_id = like.item['postId']
    assert like.item['likeStatus'] == LikeStatus.ANONYMOUSLY_LIKED

    # verify our initial like counter
    post = like_manager.post_manager.get_post(post_id)
    assert post.item['anonymousLikeCount'] == 1

    like.dislike()

    # verify the like has disappeared from dynamo
    assert like_manager.get_like(liked_by_user_id, post_id) is None

    # verify the like counter on the post has decremented
    post.refresh_item()
    assert post.item['anonymousLikeCount'] == 0


def test_dislike_fail_unable_to_decrement_like_counter(like_manager, like):
    post_id = like.item['postId']
    like_status = like.item['likeStatus']
    like_status == LikeStatus.ANONYMOUSLY_LIKED

    # verify our initial like counter
    post = like_manager.post_manager.get_post(post_id)
    assert post.item['anonymousLikeCount'] == 1

    # sneak behind the machinery being testy and lower the like count for the post
    transact = like_manager.post_manager.dynamo.transact_decrement_like_count(post_id, like_status)
    like_manager.dynamo.client.transact_write_items([transact])

    # verify the like counter has decreased
    post.refresh_item()
    assert post.item['anonymousLikeCount'] == 0

    # verify fails because can't lower count below 0
    with pytest.raises(UnableToDecrementPostLikeCounter):
        like.dislike()


def test_dislike_fail_not_liked_with_status(like_manager, like, other_user, post):
    assert like.item['likeStatus'] == LikeStatus.ANONYMOUSLY_LIKED

    # add a like to the post of the other status so that we don't have a problem decrementing that counter
    like_manager.like_post(other_user, post, LikeStatus.ONYMOUSLY_LIKED)

    # change the in-memory status so its different than the db one
    like.item['likeStatus'] = LikeStatus.ONYMOUSLY_LIKED

    # verify fails because of the mismatch (doesnt know what counter to decrement)
    with pytest.raises(NotLikedWithStatus):
        like.dislike()
