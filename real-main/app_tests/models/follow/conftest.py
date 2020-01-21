import pytest

from app.models.user import UserManager


@pytest.fixture
def user_manager(dynamo_client, cognito_client, s3_client):
    cognito_client.configure_mock(**{'get_user_attributes.return_value': {}})
    yield UserManager({'dynamo': dynamo_client, 'cognito': cognito_client, 's3_placeholder_photos': s3_client})


@pytest.fixture
def user1(user_manager):
    yield user_manager.create_cognito_only_user('uid1', 'uname1')


@pytest.fixture
def user2(user_manager):
    yield user_manager.create_cognito_only_user('uid2', 'uname2')


@pytest.fixture
def user3(user_manager):
    yield user_manager.create_cognito_only_user('uid3', 'uname3')
