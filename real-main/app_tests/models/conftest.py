from unittest.mock import Mock

import boto3
from moto import mock_dynamodb2, mock_s3
import pytest

from app.clients import CloudFrontClient, CognitoClient, DynamoClient, FacebookClient, GoogleClient, S3Client

from app_tests.dynamodb.table_schema import table_schema


@pytest.fixture
def cloudfront_client():
    yield Mock(CloudFrontClient(None, 'my-domain'))


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


# the two s3 clients need to be generated under the same `mock_s3()` context manager
# doesn't really matter which one is which, as long as within each test the two of them
# are kept straight
@pytest.fixture
def s3_clients():
    with mock_s3():
        yield {
            's3_uploads': S3Client(bucket_name='my-bucket', create_bucket=True),
            's3_placeholder_photos': S3Client(bucket_name='my-bucket-2', create_bucket=True),
        }


@pytest.fixture
def s3_client(s3_clients):
    yield s3_clients['s3_uploads']


@pytest.fixture
def s3_client_2(s3_clients):
    yield s3_clients['s3_placeholder_photos']
