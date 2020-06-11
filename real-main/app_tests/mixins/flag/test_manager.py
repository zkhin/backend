import uuid

import pytest


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user, str(uuid.uuid4()), post_manager.enums.PostType.TEXT_ONLY, text='t')


@pytest.fixture
def comment(comment_manager, user, post):
    yield comment_manager.add_comment(str(uuid.uuid4()), post.id, user.id, text='whit or lack thereof')


user2 = user
post2 = post
comment2 = comment


@pytest.mark.parametrize(
    'manager, model1, model2',
    [
        pytest.lazy_fixture(['post_manager', 'post', 'post2']),
        pytest.lazy_fixture(['comment_manager', 'comment', 'comment2']),
    ],
)
def test_unflag_all_by_user(manager, model1, model2, user2):
    # check we haven't flagged anything
    assert list(manager.flag_dynamo.generate_item_ids_by_user(user2.id)) == []
    assert model1.refresh_item().item.get('flagCount', 0) == 0
    assert model2.refresh_item().item.get('flagCount', 0) == 0

    # unflag all, check
    manager.unflag_all_by_user(user2.id)
    assert list(manager.flag_dynamo.generate_item_ids_by_user(user2.id)) == []

    # user flags both those posts
    model1.flag(user2)
    model2.flag(user2)
    assert list(manager.flag_dynamo.generate_item_ids_by_user(user2.id)) == [model1.id, model2.id]
    assert model1.refresh_item().item['flagCount'] == 1
    assert model2.refresh_item().item['flagCount'] == 1

    # unflag all, check
    manager.unflag_all_by_user(user2.id)
    assert list(manager.flag_dynamo.generate_item_ids_by_user(user2.id)) == []
    assert model1.refresh_item().item.get('flagCount', 0) == 0
    assert model2.refresh_item().item.get('flagCount', 0) == 0
