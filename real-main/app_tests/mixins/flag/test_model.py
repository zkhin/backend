import uuid

import pytest


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username=user_id)
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user.id, str(uuid.uuid4()), post_manager.enums.PostType.TEXT_ONLY, text='t')


user2 = user


@pytest.mark.parametrize('model', [pytest.lazy_fixture('post')])
def test_flag_success(model, user2):
    # check starting state
    assert model.item.get('flagCount', 0) == 0
    assert len(list(model.flag_dynamo.generate_by_item(model.id))) == 0

    # flag it, verify
    model.flag(user2)
    assert model.item.get('flagCount', 0) == 1
    assert model.refresh_item().item.get('flagCount', 0) == 1
    assert len(list(model.flag_dynamo.generate_by_item(model.id))) == 1

    # verify we can't flag the post second time
    with pytest.raises(model.flag_exceptions.FlagException, match='already been flagged'):
        model.flag(user2)
    assert model.item.get('flagCount', 0) == 1
    assert model.refresh_item().item.get('flagCount', 0) == 1


@pytest.mark.parametrize('model', [pytest.lazy_fixture('post')])
def test_cant_flag_our_own_model(model, user):
    with pytest.raises(model.flag_exceptions.FlagException, match='flag their own'):
        model.flag(user)
    assert model.item.get('flagCount', 0) == 0
    assert model.refresh_item().item.get('flagCount', 0) == 0
    assert list(model.flag_dynamo.generate_by_item(model.id)) == []


@pytest.mark.parametrize('model', [pytest.lazy_fixture('post')])
def test_cant_flag_model_of_user_thats_blocking_us(model, user, user2, block_manager):
    block_manager.block(user, user2)
    with pytest.raises(model.flag_exceptions.FlagException, match='has been blocked by owner'):
        model.flag(user2)
    assert model.item.get('flagCount', 0) == 0
    assert model.refresh_item().item.get('flagCount', 0) == 0
    assert list(model.flag_dynamo.generate_by_item(model.id)) == []


@pytest.mark.parametrize('model', [pytest.lazy_fixture('post')])
def test_cant_flag_model_of_user_we_are_blocking(model, user, user2, block_manager):
    block_manager.block(user2, user)
    with pytest.raises(model.flag_exceptions.FlagException, match='has blocked owner'):
        model.flag(user2)
    assert model.item.get('flagCount', 0) == 0
    assert model.refresh_item().item.get('flagCount', 0) == 0
    assert list(model.flag_dynamo.generate_by_item(model.id)) == []


@pytest.mark.parametrize('model', [pytest.lazy_fixture('post')])
def test_unflag(model, user2):
    # flag the model, verify worked
    model.flag(user2)
    assert model.item.get('flagCount', 0) == 1
    assert model.refresh_item().item.get('flagCount', 0) == 1
    assert len(list(model.flag_dynamo.generate_by_item(model.id))) == 1

    # unflag, verify worked
    model.unflag(user2.id)
    assert model.item.get('flagCount', 0) == 0
    assert model.refresh_item().item.get('flagCount', 0) == 0
    assert len(list(model.flag_dynamo.generate_by_item(model.id))) == 0

    # verify can't unflag if we haven't flagged
    with pytest.raises(model.flag_exceptions.FlagException, match='not been flagged'):
        model.unflag(user2.id)
