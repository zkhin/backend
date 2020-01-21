import pytest

from app.models.post import PostManager
from app.models.user import UserManager


@pytest.fixture
def post_manager(dynamo_client, s3_client):
    clients = {'dynamo': dynamo_client, 's3_uploads': s3_client}
    return PostManager(clients)


@pytest.fixture
def user_manager(dynamo_client, cognito_client, s3_clients):
    cognito_client.configure_mock(**{'get_user_attributes.return_value': {}})
    yield UserManager({
        'dynamo': dynamo_client,
        'cognito': cognito_client,
        's3_placeholder_photos': s3_clients['s3_placeholder_photos'],
    })
