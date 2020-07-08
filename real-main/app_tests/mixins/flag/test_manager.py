import logging
import uuid

import pytest

from app.models.post.enums import PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user, str(uuid.uuid4()), PostType.TEXT_ONLY, text='t')


@pytest.fixture
def comment(comment_manager, user, post):
    yield comment_manager.add_comment(str(uuid.uuid4()), post.id, user.id, text='whit or lack thereof')


@pytest.fixture
def chat(chat_manager, user, user2):
    yield chat_manager.add_direct_chat(str(uuid.uuid4()), user.id, user2.id)


@pytest.fixture
def message(chat_message_manager, chat, user):
    yield chat_message_manager.add_chat_message(str(uuid.uuid4()), 'lore ipsum', chat.id, user.id)


user2 = user
post2 = post
comment2 = comment
message2 = message


@pytest.mark.parametrize(
    'manager, model1, model2',
    [
        pytest.lazy_fixture(['post_manager', 'post', 'post2']),
        pytest.lazy_fixture(['comment_manager', 'comment', 'comment2']),
        pytest.lazy_fixture(['chat_message_manager', 'message', 'message2']),
    ],
)
def test_unflag_all_by_user(manager, model1, model2, user2):
    # check we haven't flagged anything
    assert list(manager.flag_dynamo.generate_item_ids_by_user(user2.id)) == []

    # unflag all, check
    manager.unflag_all_by_user(user2.id)
    assert list(manager.flag_dynamo.generate_item_ids_by_user(user2.id)) == []

    # user flags both those posts
    model1.flag(user2)
    model2.flag(user2)
    assert list(manager.flag_dynamo.generate_item_ids_by_user(user2.id)) == [model1.id, model2.id]

    # unflag all, check
    manager.unflag_all_by_user(user2.id)
    assert list(manager.flag_dynamo.generate_item_ids_by_user(user2.id)) == []


@pytest.mark.parametrize(
    'manager, model',
    [
        pytest.lazy_fixture(['post_manager', 'post']),
        pytest.lazy_fixture(['comment_manager', 'comment']),
        pytest.lazy_fixture(['chat_message_manager', 'message']),
    ],
)
def test_on_flag_deleted(manager, model, caplog):
    # configure and check starting state
    manager.dynamo.increment_flag_count(model.id)
    assert model.refresh_item().item.get('flagCount', 0) == 1

    # postprocess, verify flagCount is decremented
    manager.on_flag_deleted(model.id)
    assert model.refresh_item().item.get('flagCount', 0) == 0

    # postprocess again, verify fails softly
    with caplog.at_level(logging.WARNING):
        manager.on_flag_deleted(model.id)
    assert len(caplog.records) == 1
    assert 'Failed to decrement flagCount' in caplog.records[0].msg
    assert model.refresh_item().item.get('flagCount', 0) == 0
