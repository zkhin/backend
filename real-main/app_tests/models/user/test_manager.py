import logging
import re
import uuid
import unittest.mock as mock

import pytest


@pytest.fixture
def cognito_only_user1(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


cognito_only_user2 = cognito_only_user1


@pytest.fixture
def real_user(user_manager, cognito_client):
    user_id = str(uuid.uuid4())
    cognito_client.create_verified_user_pool_entry(user_id, 'real', 'real-test@real.app')
    yield user_manager.create_cognito_only_user(user_id, 'real')


def test_get_user_that_doesnt_exist(user_manager):
    resp = user_manager.get_user('nope-not-there')
    assert resp is None


def test_get_user_by_username(user_manager, cognito_only_user1):
    # check a user that doesn't exist
    user = user_manager.get_user_by_username('nope_not_there')
    assert user is None

    # check a user that exists
    user = user_manager.get_user_by_username(cognito_only_user1.username)
    assert user.id == cognito_only_user1.id


def test_create_cognito_user(user_manager, cognito_client):
    user_id = 'my-user-id'
    username = 'myusername'
    full_name = 'my-full-name'
    email = f'{username}@real.app'

    # check the user doesn't already exist
    user = user_manager.get_user(user_id)
    assert user is None

    # frontend does this part out-of-band
    cognito_client.create_verified_user_pool_entry(user_id, username, email)

    # create the user
    user = user_manager.create_cognito_only_user(user_id, username, full_name=full_name)
    assert user.id == user_id
    assert user.item['userId'] == user_id
    assert user.item['username'] == username
    assert user.item['fullName'] == full_name
    assert user.item['email'] == email
    assert 'phoneNumber' not in user.item

    # double check user got into db
    user = user_manager.get_user(user_id)
    assert user.id == user_id
    assert user.item['userId'] == user_id
    assert user.item['username'] == username
    assert user.item['fullName'] == full_name
    assert user.item['email'] == email
    assert 'phoneNumber' not in user.item

    # check cognito was set correctly
    assert user.cognito_client.get_user_attributes(user.id)['preferred_username'] == username


def test_create_cognito_user_aleady_exists(user_manager, cognito_client):
    user_id = 'my-user-id'
    username = 'orgusername'
    full_name = 'my-full-name'

    # create the user in the userpool (frontend does this in live system)
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')

    # create the user
    user = user_manager.create_cognito_only_user(user_id, username, full_name=full_name)
    assert user.id == user_id
    assert user.username == username

    # check their cognito username is as expected
    assert user.cognito_client.get_user_attributes(user.id)['preferred_username'] == username

    # try to create the user again, this time with a diff username
    with pytest.raises(user.exceptions.UserAlreadyExists):
        user_manager.create_cognito_only_user(user_id, 'diffusername')

    # verify that did not affect either dynamo, cognito or pinpoint
    user = user_manager.get_user(user_id)
    assert user.username == username
    assert user.cognito_client.get_user_attributes(user.id)['preferred_username'] == username


def test_create_cognito_user_with_email_and_phone(user_manager, cognito_client):
    user_id = 'my-user-id'
    username = 'therealuser'
    full_name = 'my-full-name'
    email = 'great@best.com'
    phone = '+123'

    # frontend does this part out-of-band: creates the user in cognito with verified email and phone
    cognito_client.boto_client.admin_create_user(
        UserPoolId=cognito_client.user_pool_id,
        Username=user_id,
        UserAttributes=[
            {'Name': 'email', 'Value': email},
            {'Name': 'email_verified', 'Value': 'true'},
            {'Name': 'phone_number', 'Value': phone},
            {'Name': 'phone_number_verified', 'Value': 'true'},
        ]
    )

    # check the user doesn't already exist
    user = user_manager.get_user(user_id)
    assert user is None

    # create the user
    user = user_manager.create_cognito_only_user(user_id, username, full_name=full_name)
    assert user.id == user_id
    assert user.item['userId'] == user_id
    assert user.item['username'] == username
    assert user.item['fullName'] == full_name
    assert user.item['email'] == email
    assert user.item['phoneNumber'] == phone

    # check cognito attrs are as expected
    cognito_attrs = user.cognito_client.get_user_attributes(user.id)
    assert cognito_attrs['preferred_username'] == username
    assert cognito_attrs['email'] == email
    assert cognito_attrs['email_verified'] == 'true'
    assert cognito_attrs['phone_number'] == phone
    assert cognito_attrs['phone_number_verified'] == 'true'


def test_create_cognito_user_with_non_verified_email_and_phone(user_manager, cognito_client):
    user_id = 'my-user-id'
    username = 'therealuser'
    full_name = 'my-full-name'
    email = 'great@best.com'
    phone = '+123'

    # frontend does this part out-of-band: creates the user in cognito with unverified email and phone
    cognito_client.boto_client.admin_create_user(
        UserPoolId=cognito_client.user_pool_id,
        Username=user_id,
        UserAttributes=[
            {'Name': 'email', 'Value': email},
            {'Name': 'email_verified', 'Value': 'false'},
            {'Name': 'phone_number', 'Value': phone},
            {'Name': 'phone_number_verified', 'Value': 'false'},
        ]
    )

    # check the user doesn't already exist
    user = user_manager.get_user(user_id)
    assert user is None

    # check can't create the user
    with pytest.raises(user_manager.exceptions.UserValidationException):
        user_manager.create_cognito_only_user(user_id, username, full_name=full_name)


def test_create_cognito_only_user_invalid_username(user_manager):
    user_id = 'my-user-id'
    invalid_username = '-'
    full_name = 'my-full-name'

    with pytest.raises(user_manager.exceptions.UserValidationException):
        user_manager.create_cognito_only_user(user_id, invalid_username, full_name=full_name)


def test_create_cognito_only_user_username_taken(user_manager, cognito_only_user1, cognito_client):
    user_id = 'uid'
    username_1 = cognito_only_user1.username.upper()
    username_2 = cognito_only_user1.username.lower()

    # frontend does this part out-of-band: creates the user in cognito, no preferred_username
    cognito_client.boto_client.admin_create_user(
        UserPoolId=cognito_client.user_pool_id,
        Username=user_id,
    )

    # moto doesn't seem to honor the 'make preferred usernames unique' setting (using it as an alias)
    # so mock it's response like to simulate that it does
    exception = user_manager.cognito_client.boto_client.exceptions.AliasExistsException({}, None)
    user_manager.cognito_client.set_user_attributes = mock.Mock(side_effect=exception)

    with pytest.raises(user_manager.exceptions.UserValidationException):
        user_manager.create_cognito_only_user(user_id, username_1)

    with pytest.raises(user_manager.exceptions.UserValidationException):
        user_manager.create_cognito_only_user(user_id, username_2)


def test_create_cognito_only_user_username_released_if_user_not_found_in_user_pool(user_manager, cognito_client):
    # two users, one username, cognito only has a user set up for one of them
    user_id_1 = 'my-user-id-1'
    user_id_2 = 'my-user-id-2'
    username = 'myUsername'
    cognito_client.boto_client.admin_create_user(
        UserPoolId=cognito_client.user_pool_id,
        Username=user_id_2,
        MessageAction='SUPPRESS',
        UserAttributes=[{
            'Name': 'email',
            'Value': 'test@real.app',
        }, {
            'Name': 'email_verified',
            'Value': 'true',
        }]
    )

    # create the first user that doesn't exist in the user pool, should fail
    with pytest.raises(user_manager.exceptions.UserValidationException):
        user_manager.create_cognito_only_user(user_id_1, username)

    # should be able to now use that same username with the other user
    user = user_manager.create_cognito_only_user(user_id_2, username)
    assert user.username == username
    assert cognito_client.get_user_attributes(user.id)['preferred_username'] == username.lower()


def test_create_cognito_only_user_follow_real_user_doesnt_exist(user_manager, cognito_client):
    # create a user, verify no followeds
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    user = user_manager.create_cognito_only_user(user_id, username)
    assert list(user.follow_manager.dynamo.generate_followed_items(user.id)) == []


def test_follow_real_user_exists(user_manager, cognito_only_user1, follow_manager, real_user):
    # verify no followers (ensures cognito_only_user1 fixture generated before real_user)
    assert list(follow_manager.dynamo.generate_followed_items(cognito_only_user1.id)) == []

    # follow that real user
    user_manager.follow_real_user(cognito_only_user1)
    followeds = list(follow_manager.dynamo.generate_followed_items(cognito_only_user1.id))
    assert len(followeds) == 1
    assert followeds[0]['followedUserId'] == real_user.id


def test_follow_real_user_doesnt_exist(user_manager, cognito_only_user1, follow_manager):
    assert list(follow_manager.dynamo.generate_followed_items(cognito_only_user1.id)) == []
    user_manager.follow_real_user(cognito_only_user1)
    assert list(follow_manager.dynamo.generate_followed_items(cognito_only_user1.id)) == []


def test_create_cognito_only_user_follow_real_user_if_exists(user_manager, cognito_client, real_user):
    # create a user, verify follows real user
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    user = user_manager.create_cognito_only_user(user_id, username)
    followeds = list(user.follow_manager.dynamo.generate_followed_items(user.id))
    assert len(followeds) == 1
    assert followeds[0]['followedUserId'] == real_user.id


def test_create_facebook_user_success(user_manager, real_user):
    fb_token = 'fb-token'
    cognito_token = 'cog-token'
    user_id = 'my-user-id'
    username = 'my_username'
    full_name = 'my-full-name'
    email = 'My@email.com'

    # set up our mocks to behave correctly
    user_manager.facebook_client.configure_mock(**{'get_verified_email.return_value': email})
    user_manager.cognito_client.create_verified_user_pool_entry = mock.Mock()
    user_manager.cognito_client.get_user_pool_id_token = mock.Mock(return_value=cognito_token)
    user_manager.cognito_client.link_identity_pool_entries = mock.Mock()

    # create the facebook user, check it is as expected
    user = user_manager.create_facebook_user(user_id, username, fb_token, full_name=full_name)
    assert user.id == user_id
    assert user.item['username'] == username
    assert user.item['fullName'] == full_name
    assert user.item['email'] == email.lower()

    # check mocks called as expected
    assert user_manager.facebook_client.mock_calls == [mock.call.get_verified_email(fb_token)]
    assert user_manager.cognito_client.create_verified_user_pool_entry.mock_calls == [
        mock.call(user_id, username, email.lower()),
    ]
    assert user_manager.cognito_client.get_user_pool_id_token.mock_calls == [mock.call(user_id)]
    assert user_manager.cognito_client.link_identity_pool_entries.mock_calls == [
        mock.call(user_id, cognito_id_token=cognito_token, facebook_access_token=fb_token),
    ]

    # check we are following the real user
    followeds = list(user.follow_manager.dynamo.generate_followed_items(user.id))
    assert len(followeds) == 1
    assert followeds[0]['followedUserId'] == real_user.id


def test_create_facebook_user_user_id_or_email_taken(user_manager, caplog):
    # configure cognito to respond as if username is already taken
    exception = user_manager.cognito_client.boto_client.exceptions.UsernameExistsException({}, None)
    user_manager.cognito_client.boto_client.admin_create_user = mock.Mock(side_effect=exception)

    with pytest.raises(user_manager.exceptions.UserValidationException):
        user_manager.create_facebook_user('uid', 'uname', 'facebook-access-token')

    # configure cognito to respond as if email is already taken
    exception = user_manager.cognito_client.boto_client.exceptions.AliasExistsException({}, None)
    user_manager.cognito_client.boto_client.admin_create_user = mock.Mock(side_effect=exception)

    with pytest.raises(user_manager.exceptions.UserValidationException):
        user_manager.create_facebook_user('uid', 'uname', 'facebook-access-token')


def test_create_google_user_success(user_manager, real_user):
    google_token = 'google-token'
    cognito_token = 'cog-token'
    user_id = 'my-user-id'
    username = 'myusername'
    full_name = 'my-full-name'
    email = 'My@email.com'  # emails from google can have upper case characters in them

    # set up our mocks to behave correctly
    user_manager.google_client.configure_mock(**{'get_verified_email.return_value': email})
    user_manager.cognito_client.create_verified_user_pool_entry = mock.Mock()
    user_manager.cognito_client.get_user_pool_id_token = mock.Mock(return_value=cognito_token)
    user_manager.cognito_client.link_identity_pool_entries = mock.Mock()

    # create the google user, check it is as expected
    user = user_manager.create_google_user(user_id, username, google_token, full_name=full_name)
    assert user.id == user_id
    assert user.item['username'] == username
    assert user.item['fullName'] == full_name
    assert user.item['email'] == email.lower()

    # check mocks called as expected
    assert user_manager.google_client.mock_calls == [mock.call.get_verified_email(google_token)]
    assert user_manager.cognito_client.create_verified_user_pool_entry.mock_calls == [
        mock.call(user_id, username, email.lower()),
    ]
    assert user_manager.cognito_client.get_user_pool_id_token.mock_calls == [mock.call(user_id)]
    assert user_manager.cognito_client.link_identity_pool_entries.mock_calls == [
        mock.call(user_id, cognito_id_token=cognito_token, google_id_token=google_token),
    ]

    # check we are following the real user
    followeds = list(user.follow_manager.dynamo.generate_followed_items(user.id))
    assert len(followeds) == 1
    assert followeds[0]['followedUserId'] == real_user.id


def test_create_google_user_user_id_or_email_taken(user_manager, caplog):

    # configure cognito to respond as if username is already taken
    exception = user_manager.cognito_client.boto_client.exceptions.UsernameExistsException({}, None)
    user_manager.cognito_client.boto_client.admin_create_user = mock.Mock(side_effect=exception)

    with pytest.raises(user_manager.exceptions.UserValidationException, match='already exists'):
        user_manager.create_google_user('uid', 'uname', 'google-id-token')

    # configure cognito to respond as if email is already taken
    exception = user_manager.cognito_client.boto_client.exceptions.AliasExistsException({}, None)
    user_manager.cognito_client.boto_client.admin_create_user = mock.Mock(side_effect=exception)

    with pytest.raises(user_manager.exceptions.UserValidationException, match='already exists'):
        user_manager.create_google_user('uid', 'uname', 'google-id-token')


def test_create_google_user_invalid_id_token(user_manager, caplog):
    google_token = 'google-token'
    user_id = 'my-user-id'
    username = 'newuser'

    # set up our mocks to behave correctly
    user_manager.google_client.configure_mock(**{'get_verified_email.side_effect': ValueError('wrong flavor')})

    # create the google user, check it is as expected
    with caplog.at_level(logging.WARNING):
        with pytest.raises(user_manager.exceptions.UserValidationException, match='wrong flavor'):
            user_manager.create_google_user(user_id, username, google_token)
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == 'WARNING'
    assert 'wrong flavor' in caplog.records[0].msg


def test_get_available_placeholder_photo_codes(user_manager):
    s3_client = user_manager.s3_placeholder_photos_client
    user_manager.placeholder_photos_directory = 'placeholder-photos'

    # check before we add any placeholder photos
    codes = user_manager.get_available_placeholder_photo_codes()
    assert codes == []

    # add a placeholder photo, check again
    path = 'placeholder-photos/black-white-cat/native.jpg'
    s3_client.put_object(path, b'placeholder', 'image/jpeg')
    codes = user_manager.get_available_placeholder_photo_codes()
    assert len(codes) == 1
    assert codes[0] == 'black-white-cat'

    # add another placeholder photo, check again
    path = 'placeholder-photos/orange-person/native.jpg'
    s3_client.put_object(path, b'placeholder', 'image/jpeg')
    path = 'placeholder-photos/orange-person/4k.jpg'
    s3_client.put_object(path, b'placeholder', 'image/jpeg')
    codes = user_manager.get_available_placeholder_photo_codes()
    assert len(codes) == 2
    assert codes[0] == 'black-white-cat'
    assert codes[1] == 'orange-person'


def test_get_random_placeholder_photo_code(user_manager):
    s3_client = user_manager.s3_placeholder_photos_client
    user_manager.placeholder_photos_directory = 'placeholder-photos'

    # check before we add any placeholder photos
    code = user_manager.get_random_placeholder_photo_code()
    assert code is None

    # add a placeholder photo, check again
    path = 'placeholder-photos/black-white-cat/native.jpg'
    s3_client.put_object(path, b'placeholder', 'image/jpeg')
    code = user_manager.get_random_placeholder_photo_code()
    assert code == 'black-white-cat'

    # add another placeholder photo, check again
    path = 'placeholder-photos/orange-person/native.jpg'
    s3_client.put_object(path, b'placeholder', 'image/jpeg')
    path = 'placeholder-photos/orange-person/4k.jpg'
    s3_client.put_object(path, b'placeholder', 'image/jpeg')
    code = user_manager.get_random_placeholder_photo_code()
    assert code in ['black-white-cat', 'orange-person']


def test_get_text_tags(user_manager, cognito_only_user1, cognito_only_user2):
    # no tags
    text = 'no tags here'
    assert user_manager.get_text_tags(text) == []

    # with tags, but not of users that exist
    text = 'hey @youDontExist and @meneither'
    assert user_manager.get_text_tags(text) == []

    # with tags, some that exist and others that dont
    username1 = cognito_only_user1.username
    username2 = cognito_only_user2.username
    text = f'hey @{username1} and @nopenope and @{username2}'
    assert sorted(user_manager.get_text_tags(text), key=lambda x: x['tag']) == sorted([
        {'tag': f'@{username1}', 'userId': cognito_only_user1.id},
        {'tag': f'@{username2}', 'userId': cognito_only_user2.id},
    ], key=lambda x: x['tag'])


def test_username_tag_regex(user_manager):
    reg = user_manager.username_tag_regex

    # no tags
    assert re.findall(reg, '') == []
    assert re.findall(reg, 'no tags here') == []

    # basic tags
    assert re.findall(reg, 'hi @you how @are @you') == ['@you', '@are', '@you']
    assert re.findall(reg, 'hi @y3o@m.e@ever_yone') == ['@y3o', '@m.e', '@ever_yone']

    # near misses
    assert re.findall(reg, 'too @34 @.. @go!forit @no-no') == []

    # uglies
    assert re.findall(reg, 'hi @._._ @4_. @A_A\n@B.4\r@333!?') == ['@._._', '@4_.', '@A_A', '@B.4', '@333']
