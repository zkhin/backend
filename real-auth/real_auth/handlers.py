from .dispatch import ClientException, handler
from .clients import CognitoClient
from .enums import UsernameStatus
from .validate import validate_username

cognito_client = CognitoClient()


@handler
def get_username_status(event, context):
    username = (event['queryStringParameters'] or {}).get('username', None)
    if username is None:
        raise ClientException('Query parameter `username` is required')

    if not validate_username(username):
        status = UsernameStatus.INVALID
    elif cognito_client.is_username_available(username):
        status = UsernameStatus.AVAILABLE
    else:
        status = UsernameStatus.NOT_AVAILABLE

    return {'status': status}
