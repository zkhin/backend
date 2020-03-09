import base64
import json
from os import path
from unittest.mock import Mock

import boto3
from moto import mock_dynamodb2, mock_s3, mock_secretsmanager
import pytest

from app.clients import (CloudFrontClient, CognitoClient, DynamoClient, FacebookClient, GoogleClient,
                         MediaConvertClient, S3Client, SecretsManagerClient)
from app.models.album import AlbumManager
from app.models.block import BlockManager
from app.models.comment import CommentManager
from app.models.feed import FeedManager
from app.models.flag import FlagManager
from app.models.follow import FollowManager
from app.models.followed_first_story import FollowedFirstStoryManager
from app.models.like import LikeManager
from app.models.media import MediaManager
from app.models.post import PostManager
from app.models.post_view import PostViewManager
from app.models.trending import TrendingManager
from app.models.user import UserManager

from app_tests.dynamodb.table_schema import table_schema

tiny_path = path.join(path.dirname(__file__), '..', 'fixtures', 'tiny.jpg')


@pytest.fixture
def image_data():
    with open(tiny_path, 'rb') as fh:
        yield fh.read()


@pytest.fixture
def image_data_b64(image_data):
    yield base64.b64encode(image_data)


@pytest.fixture
def post_verification_api_creds():
    yield {
        'key': 'the-api-key',
        'root': 'https://mockmock.mock/',
    }


@pytest.fixture
def mock_post_verification_api(requests_mock, cloudfront_client, post_verification_api_creds):
    cloudfront_client.configure_mock(**{
        'generate_presigned_url.return_value': 'https://the-image.com',
    })
    api_url = post_verification_api_creds['root'] + 'verify/image'
    resp_json = {
        'errors': [],
        'data': {
            'isVerified': False,
        }
    }
    requests_mock.post(api_url, json=resp_json)


@pytest.fixture
def secrets_manager_client(post_verification_api_creds):
    with mock_secretsmanager():
        post_verification_name = 'KeyForPV'
        post_verification_secret_string = json.dumps(post_verification_api_creds)
        client = SecretsManagerClient(post_verification_api_creds_name=post_verification_name)
        client.boto_client.create_secret(Name=post_verification_name, SecretString=post_verification_secret_string)
        yield client


@pytest.fixture
def cloudfront_client():
    yield Mock(CloudFrontClient(None, 'my-domain'))


@pytest.fixture
def mediaconvert_client():
    endpoint = 'https://my-media-convert-endpoint.com'
    yield Mock(MediaConvertClient(endpoint=endpoint, aws_region='aws-region', aws_account_id='aws-aid',
                                  role_arn='role-arn', uploads_bucket='uploads-bucket'))


@pytest.fixture
def cognito_client():
    mocked = Mock(CognitoClient('my-user-pool-id', 'my-client-id'))
    mocked.boto_client = boto3.client('cognito-idp')  # allows access to the exceptions classes
    yield mocked


@pytest.fixture
def dynamo_client():
    with mock_dynamodb2():
        yield DynamoClient(table_name='my-table', create_table_schema=table_schema)


@pytest.fixture
def facebook_client():
    yield Mock(FacebookClient())


@pytest.fixture
def google_client():
    yield Mock(GoogleClient())


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
def comment_manager(dynamo_client, user_manager):
    yield CommentManager({'dynamo': dynamo_client}, managers={'user': user_manager})


@pytest.fixture
def feed_manager(dynamo_client):
    yield FeedManager({'dynamo': dynamo_client})


@pytest.fixture
def flag_manager(dynamo_client):
    yield FlagManager({'dynamo': dynamo_client})


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
def media_manager(dynamo_client, s3_uploads_client):
    yield MediaManager({'dynamo': dynamo_client, 's3_uploads': s3_uploads_client})


@pytest.fixture
def post_manager(dynamo_client, s3_uploads_client, cloudfront_client, secrets_manager_client):
    yield PostManager({
        'dynamo': dynamo_client,
        's3_uploads': s3_uploads_client,
        'cloudfront': cloudfront_client,
        'secrets_manager': secrets_manager_client,
    })


@pytest.fixture
def post_view_manager(dynamo_client):
    yield PostViewManager({'dynamo': dynamo_client})


@pytest.fixture
def trending_manager(dynamo_client):
    yield TrendingManager({'dynamo': dynamo_client})


@pytest.fixture
def user_manager(cloudfront_client, dynamo_client, s3_uploads_client, s3_placeholder_photos_client, cognito_client,
                 facebook_client, google_client):
    cognito_client.configure_mock(**{'get_user_attributes.return_value': {}})
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
