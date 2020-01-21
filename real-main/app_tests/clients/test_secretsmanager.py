import json

from moto import mock_secretsmanager
import pytest

from app.clients import SecretsManagerClient

cloudfront_key_pair_name = 'KeyForCloudFront'
post_verification_api_creds_name = 'KeyForPV'


@pytest.fixture
def client():
    with mock_secretsmanager():
        yield SecretsManagerClient(cloudfront_key_pair_name=cloudfront_key_pair_name,
                                   post_verification_api_creds_name=post_verification_api_creds_name)


def test_retrieve_cloudfront_key_pair(client):
    value = {
        'kid': 'the-key-id',
        'public': 'public-key-content',
        'private': 'private-key-content',
    }

    # add the secret, then remove it
    client.boto_client.create_secret(Name=cloudfront_key_pair_name, SecretString=json.dumps(value))
    client.boto_client.delete_secret(SecretId=cloudfront_key_pair_name)

    # secret is not in there - test we cannot retrieve it
    with pytest.raises(Exception):
        client.get_cloudfront_key_pair()

    # restore the value in there, test we can retrieve it
    client.boto_client.restore_secret(SecretId=cloudfront_key_pair_name)
    assert client.get_cloudfront_key_pair() == value

    # test caching: remove the secret from the backend store, check again
    client.boto_client.delete_secret(SecretId=cloudfront_key_pair_name)
    assert client.get_cloudfront_key_pair() == value


def test_retrieve_post_verification_api_creds(client):
    value = {
        'key': 'the-api-key',
        'root': 'https://api-root.root',
    }

    # add the secret, then remove it
    client.boto_client.create_secret(Name=post_verification_api_creds_name, SecretString=json.dumps(value))
    client.boto_client.delete_secret(SecretId=post_verification_api_creds_name)

    # secret is not in there - test we cannot retrieve it
    with pytest.raises(Exception):
        client.get_post_verification_api_creds()

    # restore the value in there, test we can retrieve it
    client.boto_client.restore_secret(SecretId=post_verification_api_creds_name)
    assert client.get_post_verification_api_creds() == value

    # test caching: remove the secret from the backend store, check again
    client.boto_client.delete_secret(SecretId=post_verification_api_creds_name)
    assert client.get_post_verification_api_creds() == value
