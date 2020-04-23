import base64
from os import path
from unittest.mock import Mock

from moto import mock_cognitoidp, mock_dynamodb2, mock_s3
import pytest

from app.clients import (AppSyncClient, CloudFrontClient, CognitoClient, DynamoClient, FacebookClient, GoogleClient,
                         MediaConvertClient, PostVerificationClient, S3Client)
from app.models.album import AlbumManager
from app.models.block import BlockManager
from app.models.chat import ChatManager
from app.models.chat_message import ChatMessageManager
from app.models.comment import CommentManager
from app.models.feed import FeedManager
from app.models.follow import FollowManager
from app.models.followed_first_story import FollowedFirstStoryManager
from app.models.like import LikeManager
from app.models.media import MediaManager
from app.models.post import PostManager
from app.models.trending import TrendingManager
from app.models.user import UserManager
from app.models.view import ViewManager

from app_tests.dynamodb.table_schema import table_schema

grant_path = path.join(path.dirname(__file__), '..', 'fixtures', 'grant.jpg')
tiny_path = path.join(path.dirname(__file__), '..', 'fixtures', 'tiny.jpg')


@pytest.fixture
def image_data():
    with open(tiny_path, 'rb') as fh:
        yield fh.read()


@pytest.fixture
def image_data_b64(image_data):
    yield base64.b64encode(image_data)


@pytest.fixture
def grant_data():
    with open(grant_path, 'rb') as fh:
        yield fh.read()


@pytest.fixture
def grant_data_b64(grant_data):
    yield base64.b64encode(grant_data)


@pytest.fixture
def appsync_client():
    yield Mock(AppSyncClient(appsync_graphql_url='my-graphql-url'))


@pytest.fixture
def cloudfront_client():
    yield Mock(CloudFrontClient(None, 'my-domain'))


@pytest.fixture
def mediaconvert_client():
    endpoint = 'https://my-media-convert-endpoint.com'
    yield Mock(MediaConvertClient(endpoint=endpoint, aws_region='aws-region', aws_account_id='aws-aid',
                                  role_arn='role-arn', uploads_bucket='uploads-bucket'))


@pytest.fixture
def post_verification_client():
    # by default, all images pass verification
    yield Mock(PostVerificationClient(lambda: None), **{'verify_image.return_value': True})


@pytest.fixture
def cognito_client():
    with mock_cognitoidp():
        cognito_client = CognitoClient('dummy', 'my-client-id')
        resp = cognito_client.boto_client.create_user_pool(
            PoolName='user-pool-name',
            AliasAttributes=['phone_number', 'email', 'preferred_username'],  # but doesnt appear to force uniqueness
        )
        cognito_client.user_pool_id = resp['UserPool']['Id']
        yield cognito_client


@pytest.fixture
def dynamo_client():
    with mock_dynamodb2():
        yield DynamoClient(table_name='my-table', create_table_schema=table_schema)


@pytest.fixture
def facebook_client():
    yield Mock(FacebookClient())


@pytest.fixture
def google_client():
    yield Mock(GoogleClient(lambda: {}))


# can't nest the moto context managers, it appears. To be able to use two mocked S3 buckets
# they thus need to be yielded under the same context manager
@pytest.fixture
def s3_clients():
    with mock_s3():
        yield {
            'uploads': S3Client(bucket_name='uploads-bucket', create_bucket=True),
            'placeholder-photos': S3Client(bucket_name='placerholder-photos-bucket', create_bucket=True),
        }


@pytest.fixture
def s3_uploads_client(s3_clients):
    yield s3_clients['uploads']


@pytest.fixture
def s3_placeholder_photos_client(s3_clients):
    yield s3_clients['placeholder-photos']


@pytest.fixture
def album_manager(dynamo_client, s3_uploads_client, cloudfront_client):
    yield AlbumManager({'dynamo': dynamo_client, 's3_uploads': s3_uploads_client, 'cloudfront': cloudfront_client})


@pytest.fixture
def block_manager(dynamo_client):
    yield BlockManager({'dynamo': dynamo_client})


@pytest.fixture
def chat_manager(dynamo_client, appsync_client):
    yield ChatManager({'appsync': appsync_client, 'dynamo': dynamo_client})


@pytest.fixture
def chat_message_manager(dynamo_client, appsync_client, cloudfront_client):
    yield ChatMessageManager({'appsync': appsync_client, 'cloudfront': cloudfront_client, 'dynamo': dynamo_client})


@pytest.fixture
def comment_manager(dynamo_client, user_manager):
    yield CommentManager({'dynamo': dynamo_client}, managers={'user': user_manager})


@pytest.fixture
def feed_manager(dynamo_client):
    yield FeedManager({'dynamo': dynamo_client})


@pytest.fixture
def follow_manager(dynamo_client):
    yield FollowManager({'dynamo': dynamo_client})


@pytest.fixture
def ffs_manager(dynamo_client):
    yield FollowedFirstStoryManager({'dynamo': dynamo_client})


@pytest.fixture
def like_manager(dynamo_client):
    yield LikeManager({'dynamo': dynamo_client})


@pytest.fixture
def media_manager(dynamo_client, s3_uploads_client, cloudfront_client):
    yield MediaManager({'dynamo': dynamo_client, 'cloudfront': cloudfront_client, 's3_uploads': s3_uploads_client})


@pytest.fixture
def post_manager(appsync_client, dynamo_client, s3_uploads_client, cloudfront_client, post_verification_client):
    yield PostManager({
        'appsync': appsync_client,
        'dynamo': dynamo_client,
        's3_uploads': s3_uploads_client,
        'cloudfront': cloudfront_client,
        'post_verification': post_verification_client,
    })


@pytest.fixture
def trending_manager(dynamo_client):
    yield TrendingManager({'dynamo': dynamo_client})


@pytest.fixture
def user_manager(cloudfront_client, dynamo_client, s3_uploads_client, s3_placeholder_photos_client, cognito_client,
                 facebook_client, google_client):
    clients = {
        'cloudfront': cloudfront_client,
        'dynamo': dynamo_client,
        's3_uploads': s3_uploads_client,
        's3_placeholder_photos': s3_placeholder_photos_client,
        'cognito': cognito_client,
        'facebook': facebook_client,
        'google': google_client,
    }
    yield UserManager(clients)


@pytest.fixture
def view_manager(dynamo_client):
    yield ViewManager({'appsync': appsync_client, 'dynamo': dynamo_client})
