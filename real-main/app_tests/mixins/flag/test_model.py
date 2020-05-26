import logging
import unittest.mock as mock
import uuid

import pytest

import app.models.user.enums as user_enums


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username=user_id)
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user, str(uuid.uuid4()), post_manager.enums.PostType.TEXT_ONLY, text='t')


@pytest.fixture
def comment(comment_manager, post, user):
    yield comment_manager.add_comment(str(uuid.uuid4()), post.id, user.id, 'lore ipsum')


user2 = user
user3 = user
user4 = user
user5 = user
user6 = user
user7 = user


@pytest.mark.parametrize('model', [pytest.lazy_fixture('post'), pytest.lazy_fixture('comment')])
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


@pytest.mark.parametrize('model', [pytest.lazy_fixture('post'), pytest.lazy_fixture('comment')])
def test_cant_flag_our_own_model(model, user):
    with pytest.raises(model.flag_exceptions.FlagException, match='flag their own'):
        model.flag(user)
    assert model.item.get('flagCount', 0) == 0
    assert model.refresh_item().item.get('flagCount', 0) == 0
    assert list(model.flag_dynamo.generate_by_item(model.id)) == []


@pytest.mark.parametrize('model', [pytest.lazy_fixture('post'), pytest.lazy_fixture('comment')])
def test_cant_flag_model_of_user_thats_blocking_us(model, user, user2, block_manager):
    block_manager.block(user, user2)
    with pytest.raises(model.flag_exceptions.FlagException, match='has been blocked by owner'):
        model.flag(user2)
    assert model.item.get('flagCount', 0) == 0
    assert model.refresh_item().item.get('flagCount', 0) == 0
    assert list(model.flag_dynamo.generate_by_item(model.id)) == []


@pytest.mark.parametrize('model', [pytest.lazy_fixture('post'), pytest.lazy_fixture('comment')])
def test_cant_flag_model_of_user_we_are_blocking(model, user, user2, block_manager):
    block_manager.block(user2, user)
    with pytest.raises(model.flag_exceptions.FlagException, match='has blocked owner'):
        model.flag(user2)
    assert model.item.get('flagCount', 0) == 0
    assert model.refresh_item().item.get('flagCount', 0) == 0
    assert list(model.flag_dynamo.generate_by_item(model.id)) == []


@pytest.mark.parametrize('model', [pytest.lazy_fixture('post'), pytest.lazy_fixture('comment')])
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


@pytest.mark.parametrize('model', [pytest.lazy_fixture('post'), pytest.lazy_fixture('comment')])
def test_is_crowdsourced_forced_removal_criteria_met(model, user2, user3, user4, user5, user6, user7):
    # should archive if over 5 users have viewed the model and more than 10% have flagged it
    # one flag, verify shouldn't force-archive
    model.flag(user2)
    assert model.is_crowdsourced_forced_removal_criteria_met() is False

    # get 5 views, verify still shouldn't force-archive
    model.record_view_count(user2.id, 1)
    model.record_view_count(user3.id, 1)
    model.record_view_count(user4.id, 1)
    model.record_view_count(user5.id, 1)
    model.record_view_count(user6.id, 1)
    model.refresh_item()
    assert model.is_crowdsourced_forced_removal_criteria_met() is False

    # get a 6th view, verify should force-archive now
    model.record_view_count(user7.id, 1)
    model.refresh_item()
    assert model.is_crowdsourced_forced_removal_criteria_met() is True


@pytest.mark.parametrize('model', [pytest.lazy_fixture('post'), pytest.lazy_fixture('comment')])
def test_flag_force_remove_by_crowdsourced_criteria(model, user2, user3, caplog):
    model.remove_from_flagging = mock.Mock()

    # test without force-removal
    model.is_crowdsourced_forced_removal_criteria_met = mock.Mock(return_value=False)
    with caplog.at_level(logging.WARNING):
        model.flag(user2)
    assert len(caplog.records) == 0
    assert model.remove_from_flagging.mock_calls == []

    # test with force-removal
    model.is_crowdsourced_forced_removal_criteria_met = mock.Mock(return_value=True)
    with caplog.at_level(logging.WARNING):
        model.flag(user3)
    assert len(caplog.records) == 1
    assert 'Force removing' in caplog.records[0].msg
    assert model.id in caplog.records[0].msg
    assert model.remove_from_flagging.mock_calls == [mock.call()]


@pytest.mark.parametrize('model', [pytest.lazy_fixture('post'), pytest.lazy_fixture('comment')])
def test_flag_force_archive_by_admin(model, user2, caplog):
    model.remove_from_flagging = mock.Mock()
    model.flag_admin_usernames = (user2.username,)
    with caplog.at_level(logging.WARNING):
        model.flag(user2)
    assert len(caplog.records) == 1
    assert 'Force removing' in caplog.records[0].msg
    assert model.id in caplog.records[0].msg
    assert model.remove_from_flagging.mock_calls == [mock.call()]


@pytest.mark.parametrize('model', [pytest.lazy_fixture('post'), pytest.lazy_fixture('comment')])
def test_flag_force_disable_user(model, user2, user3, caplog):
    model.is_crowdsourced_forced_removal_criteria_met = mock.Mock(return_value=True)
    model.remove_from_flagging = mock.Mock()
    model.user.set_user_status = mock.Mock()

    # test without force disabling triggered
    model.is_user_forced_disabling_criteria_met = mock.Mock(return_value=False)
    with caplog.at_level(logging.WARNING):
        model.flag(user2)
    assert model.remove_from_flagging.mock_calls == [mock.call()]
    assert model.user.set_user_status.mock_calls == []

    # check the logs
    assert len(caplog.records) == 1
    assert 'Force removing' in caplog.records[0].msg
    assert model.id in caplog.records[0].msg

    # test with force disabling triggered
    caplog.clear()
    model.remove_from_flagging.reset_mock()
    model.is_user_forced_disabling_criteria_met = mock.Mock(return_value=True)
    with caplog.at_level(logging.WARNING):
        model.flag(user3)
    assert model.remove_from_flagging.mock_calls == [mock.call()]
    assert model.user.set_user_status.mock_calls == [mock.call(user_enums.UserStatus.DISABLED)]

    # check the logs
    assert len(caplog.records) == 3
    assert 'Force removing' in caplog.records[0].msg
    assert model.id in caplog.records[0].msg
    assert 'Force disabling' in caplog.records[1].msg
    assert model.user_id in caplog.records[1].msg
    assert 'USER_FORCE_DISABLED' in caplog.records[2].msg
    assert model.user_id in caplog.records[2].msg
    assert model.user.username in caplog.records[2].msg
