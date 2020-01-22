import pytest

from app.models.block import BlockManager
from app.models.follow import FollowManager
from app.models.like import LikeManager
from app.models.post import PostManager
from app.models.user import UserManager


@pytest.fixture
def follow_manager(dynamo_client):
    yield FollowManager({'dynamo': dynamo_client})


@pytest.fixture
def block_manager(dynamo_client):
    yield BlockManager({'dynamo': dynamo_client})


@pytest.fixture
def like_manager(dynamo_client):
    yield LikeManager({'dynamo': dynamo_client})


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


@pytest.fixture
def post(dynamo_client, like_manager, user_manager, post_manager):
    posted_by_user = user_manager.create_cognito_only_user('pbuid', 'pbUname')
    yield post_manager.add_post(posted_by_user.id, 'pid', text='lore ipsum')


@pytest.fixture
def post2(dynamo_client, like_manager, user_manager, post_manager):
    posted_by_user = user_manager.create_cognito_only_user('pbuid2', 'pbUname2')
    yield post_manager.add_post(posted_by_user.id, 'pid2', text='lore ipsum')
