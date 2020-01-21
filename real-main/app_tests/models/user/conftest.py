import pytest

from app.models.user import UserManager


@pytest.fixture
def user_manager(cloudfront_client, dynamo_client, s3_client, s3_client_2, cognito_client, facebook_client,
                 google_client):
    cognito_client.configure_mock(**{'get_user_attributes.return_value': {}})
    clients = {
        'cloudfront': cloudfront_client,
        'dynamo': dynamo_client,
        's3_uploads': s3_client,
        's3_placeholder_photos': s3_client_2,
        'cognito': cognito_client,
        'facebook': facebook_client,
        'google': google_client,
    }
    yield UserManager(clients)
