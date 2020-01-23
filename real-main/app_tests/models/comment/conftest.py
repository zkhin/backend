import pytest

from app.models.block import BlockManager
from app.models.comment import CommentManager
from app.models.follow import FollowManager
from app.models.post import PostManager
from app.models.user import UserManager


@pytest.fixture
def comment_manager(dynamo_client, user_manager):
    yield CommentManager({'dynamo': dynamo_client}, managers={'user': user_manager})


@pytest.fixture
def block_manager(dynamo_client):
    yield BlockManager({'dynamo': dynamo_client})


@pytest.fixture
def follow_manager(dynamo_client):
    yield FollowManager({'dynamo': dynamo_client})


@pytest.fixture
def post_manager(dynamo_client):
    yield PostManager({'dynamo': dynamo_client})


@pytest.fixture
def user_manager(dynamo_client, cognito_client, s3_clients):
    cognito_client.configure_mock(**{'get_user_attributes.return_value': {}})
    yield UserManager({
        'dynamo': dynamo_client,
        'cognito': cognito_client,
        's3_placeholder_photos': s3_clients['s3_placeholder_photos'],
    })
