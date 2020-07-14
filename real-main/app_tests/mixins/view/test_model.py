import uuid

import pytest

from app.mixins.view.enums import ViewedStatus
from app.models.post.enums import PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user
user3 = user


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user, str(uuid.uuid4()), PostType.TEXT_ONLY, text='t')


@pytest.fixture
def comment(post_manager, comment_manager, post, user):
    post = post_manager.add_post(user, str(uuid.uuid4()), PostType.TEXT_ONLY, text='t')
    yield comment_manager.add_comment(str(uuid.uuid4()), post.id, user.id, 'witty comment')


@pytest.fixture
def chat(chat_manager, user, user2):
    yield chat_manager.add_direct_chat(str(uuid.uuid4()), user.id, user2.id)


@pytest.mark.parametrize(
    'model', pytest.lazy_fixture(['post', 'comment', 'chat']),
)
def test_owner_cant_record_views_has_always_alread_viewed(model, user2):
    # check owner has always viewed it
    assert model.get_viewed_status(model.user_id) == ViewedStatus.VIEWED
    model.record_view_count(model.user_id, 5)
    assert model.get_viewed_status(model.user_id) == ViewedStatus.VIEWED


@pytest.mark.parametrize(
    'model', pytest.lazy_fixture(['post', 'comment', 'chat']),
)
def test_record_get_and_delete_views(model, user2, user3):
    # check users have not viewed it
    assert model.get_viewed_status(user2.id) == ViewedStatus.NOT_VIEWED
    assert model.get_viewed_status(user3.id) == ViewedStatus.NOT_VIEWED

    # record some views by the rando, check recorded to dynamo
    model.record_view_count(user2.id, 5)
    assert model.get_viewed_status(user2.id) == ViewedStatus.VIEWED
    view_item = model.view_dynamo.get_view(model.id, user2.id)
    assert view_item['viewCount'] == 5
    assert user2.id in view_item['sortKey']
    assert view_item['firstViewedAt']
    assert view_item['firstViewedAt'] == view_item['lastViewedAt']
    first_viewed_at = view_item['firstViewedAt']

    # record some more views by the rando, check recorded to dynamo
    model.record_view_count(user2.id, 3)
    assert model.get_viewed_status(user2.id) == ViewedStatus.VIEWED
    view_item = model.view_dynamo.get_view(model.id, user2.id)
    assert view_item['viewCount'] == 8
    assert view_item['firstViewedAt'] == first_viewed_at
    assert view_item['lastViewedAt'] > first_viewed_at

    # record views by the other user too, check their viewed status also changed
    model.record_view_count(user3.id, 3)
    assert model.get_viewed_status(user3.id) == ViewedStatus.VIEWED
    assert model.view_dynamo.get_view(model.id, user3.id)

    # delete all the views on the item, check they are gone
    model.delete_views()
    assert model.view_dynamo.get_view(model.id, user2.id) is None
    assert model.view_dynamo.get_view(model.id, user3.id) is None
    assert model.get_viewed_status(user2.id) == ViewedStatus.NOT_VIEWED
    assert model.get_viewed_status(user3.id) == ViewedStatus.NOT_VIEWED
