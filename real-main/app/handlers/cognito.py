import logging
import os
import re

logger = logging.getLogger()

COGNITO_TESTING_CLIENT_ID = os.environ.get('COGNITO_USER_POOL_TESTING_CLIENT_ID')

username_re = re.compile(r'us-east-1:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z')


class CognitoClientException(Exception):
    pass


def pre_sign_up(event, context):
    validate_username_format(event)
    validate_user_attribute_lowercase(event, 'email')

    # AWS doesn't let you set preferred_username in this call because the user isn't confirmed yet
    # validate_user_attribute_lowercase(event, 'preferred_username')

    client_id = event['callerContext']['clientId']
    if client_id == COGNITO_TESTING_CLIENT_ID:
        # make sure users created by the testing client are marked as such
        # so they can be identified and deleted later on, if testing cleanup doesn't catch them
        family_name = get_user_attribute(event, 'family_name')
        if family_name != 'TESTER':
            logger.warning(f"The testing client tried to create a user with family_name: '{family_name}'")
            return {}

        # auto-confirm & verify users created by the testing client
        # so they can login without receiving an email/text
        event['response']['autoConfirmUser'] = True
        if get_user_attribute(event, 'email'):
            event['response']['autoVerifyEmail'] = True
        if get_user_attribute(event, 'phone_number'):
            event['response']['autoVerifyPhone'] = True

    return event


def pre_auth(event, context):
    validate_username_format(event)
    validate_user_attribute_lowercase(event, 'email')
    validate_user_attribute_lowercase(event, 'preferred_username')
    return event


def custom_message(event, context):
    if event['triggerSource'] == 'CustomMessage_SignUp':
        username = event['userName']
        code = event['request']['codeParameter']
        deepurl = f'real.app://Auth?action=signupConfirm&username={username}&confirmationCode={code}'
        event['response']['smsMessage'] = f'Welcome to REAL. Your confirmation code is {code}'
        event['response']['emailSubject'] = 'Welcome to REAL'
        event['response']['emailMessage'] = (
            f'Welcome to REAL. Your confirmation code is {code}. <a href="{deepurl}">{deepurl}</a>'
        )
    return event


def get_user_attribute(event, attr_name):
    return (event['request']['userAttributes'] or {}).get(attr_name)


def validate_username_format(event):
    cognito_username = event.get('userName', '')
    if not username_re.match(cognito_username):
        raise CognitoClientException(f'Invalid username format: `{cognito_username}`')


def validate_user_attribute_lowercase(event, attr_name):
    "If value is present, ensure it is lowercase. Passes if attribute is missing"
    attr = get_user_attribute(event, attr_name)
    if attr and any([c.isupper() for c in attr]):
        raise CognitoClientException(f"User's {attr_name} '{attr}' has upper case characters")
