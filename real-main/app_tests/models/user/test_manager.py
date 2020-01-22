import re
from unittest.mock import call

import pytest


def test_get_user_that_doesnt_exist(user_manager):
    resp = user_manager.get_user('nope-not-there')
    assert resp is None


def test_get_user_by_username(user_manager):
    user_id = 'my-user-id'
    username = 'therealuser'

    # check user doesn't exist
    user = user_manager.get_user_by_username(username)
    assert user is None

    # create the user
    user = user_manager.create_cognito_only_user(user_id, username)
    assert user.id == user_id
    assert user.item['userId'] == user_id
    assert user.item['username'] == username

    # check exists
    user = user_manager.get_user_by_username(username)
    assert user.id == user_id
    assert user.item['userId'] == user_id
    assert user.item['username'] == username


def test_create_cognito_user(user_manager):
    user_id = 'my-user-id'
    username = 'therealuser'
    full_name = 'my-full-name'

    # check the user doesn't already exist
    user = user_manager.get_user(user_id)
    assert user is None

    # create the user
    user = user_manager.create_cognito_only_user(user_id, username, full_name=full_name)
    assert user.id == user_id
    assert user.item['userId'] == user_id
    assert user.item['username'] == username
    assert user.item['fullName'] == full_name
    assert 'email' not in user.item
    assert 'phoneNumber' not in user.item

    # verify social services called as expected
    assert user_manager.cognito_client.mock_calls == [
        call.get_user_attributes(user_id),
        call.set_user_attributes(user_id, {'preferred_username': username}),
    ]

    # double check user got into db
    user = user_manager.get_user(user_id)
    assert user.id == user_id
    assert user.item['userId'] == user_id
    assert user.item['username'] == username
    assert user.item['fullName'] == full_name
    assert 'email' not in user.item
    assert 'phoneNumber' not in user.item


def test_create_cognito_user_with_email_and_phone(user_manager):
    user_id = 'my-user-id'
    username = 'therealuser'
    full_name = 'my-full-name'
    email = 'great@best.com'
    phone = '+123'

    cognito_user_attrs = {
        'email': email,
        'email_verified': True,
        'phone_number': phone,
        'phone_number_verified': True,
    }
    user_manager.cognito_client.configure_mock(**{'get_user_attributes.return_value': cognito_user_attrs})

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

    # verify social services called as expected
    assert user_manager.cognito_client.mock_calls == [
        call.get_user_attributes(user_id),
        call.set_user_attributes(user_id, {'preferred_username': username}),
    ]


def test_create_cognito_user_with_non_verified_email_and_phone(user_manager):
    user_id = 'my-user-id'
    username = 'therealuser'
    full_name = 'my-full-name'
    email = 'great@best.com'
    phone = '+123'

    cognito_user_attrs = {
        'email': email,
        'email_verified': False,
        'phone_number': phone,
        'phone_number_verified': False,
    }
    user_manager.cognito_client.configure_mock(**{'get_user_attributes.return_value': cognito_user_attrs})

    # check the user doesn't already exist
    user = user_manager.get_user(user_id)
    assert user is None

    # create the user
    user = user_manager.create_cognito_only_user(user_id, username, full_name=full_name)
    assert user.id == user_id
    assert user.item['userId'] == user_id
    assert user.item['username'] == username
    assert user.item['fullName'] == full_name
    assert 'email' not in user.item
    assert 'phoneNumber' not in user.item

    # verify social services called as expected
    assert user_manager.cognito_client.mock_calls == [
        call.get_user_attributes(user_id),
        call.set_user_attributes(user_id, {'preferred_username': username}),
    ]


def test_create_cognito_only_user_invalid_username(user_manager):
    user_id = 'my-user-id'
    invalid_username = '-'
    full_name = 'my-full-name'

    with pytest.raises(user_manager.exceptions.UserValidationException):
        user_manager.create_cognito_only_user(user_id, invalid_username, full_name=full_name)


def test_create_cognito_only_user_username_taken(user_manager):
    user_id_1 = 'my-user-id-1'
    user_id_2 = 'my-user-id-2'
    username_1 = 'REAL'
    username_2 = 'real'

    # create the first user
    user_manager.create_cognito_only_user(user_id_1, username_1)

    # configure cognito to respond as if username is already taken
    exception = user_manager.cognito_client.boto_client.exceptions.AliasExistsException({}, None)
    user_manager.cognito_client.configure_mock(**{'set_user_attributes.side_effect': exception})

    # the second should fail with a username clash
    with pytest.raises(user_manager.exceptions.UserValidationException):
        user_manager.create_cognito_only_user(user_id_2, username_2)


def test_create_cognito_only_user_username_released_if_user_not_found_in_cognito_user_pool(user_manager):
    user_id_1 = 'my-user-id-1'
    user_id_2 = 'my-user-id-2'
    username = 'myUsername'

    # configure cognito to respond as if user doesn't exist
    exception = user_manager.cognito_client.boto_client.exceptions.UserNotFoundException({}, None)
    user_manager.cognito_client.configure_mock(**{'get_user_attributes.side_effect': exception})

    # create the first user, should fail
    with pytest.raises(user_manager.exceptions.UserValidationException):
        user_manager.create_cognito_only_user(user_id_1, username)

    # cognito will now respond normally, someone else should be able to use the username now
    user_manager.cognito_client.get_user_attributes.reset_mock(side_effect=True)
    user_manager.create_cognito_only_user(user_id_2, username)


def test_follow_real_user_if_exists(user_manager):
    # create a user, verify no followeds
    user = user_manager.create_cognito_only_user('uid1', 'uname1')
    assert list(user.follow_manager.dynamo.generate_followed_items(user.id)) == []

    # real user doesn't exist, so this is a no-op
    user_manager.follow_real_user(user)
    assert list(user.follow_manager.dynamo.generate_followed_items(user.id)) == []

    # create the rels user
    real_user = user_manager.create_cognito_only_user('real-uid', 'real')

    # now following them if they exist should work
    user_manager.follow_real_user(user)
    followeds = list(user.follow_manager.dynamo.generate_followed_items(user.id))
    assert len(followeds) == 1
    assert followeds[0]['followedUserId'] == real_user.id


def test_create_cognito_only_user_follow_real_user_if_exists(user_manager):
    # create a 'real' user, they should not follow anyone
    real_user = user_manager.create_cognito_only_user('real-uid', 'real')
    assert list(real_user.follow_manager.dynamo.generate_followed_items(real_user.id)) == []

    # create a user with a 'real' user in the DB, should follow real user
    user = user_manager.create_cognito_only_user('uid2', 'uname2')
    followeds = list(user.follow_manager.dynamo.generate_followed_items(user.id))
    assert len(followeds) == 1
    assert followeds[0]['followedUserId'] == real_user.id


def test_create_facebook_user_success(user_manager):
    fb_token = 'fb-token'
    cognito_token = 'cog-token'
    user_id = 'my-user-id'
    username = 'therealuser'
    full_name = 'my-full-name'
    email = 'My@email.com'

    # create a 'real' user, they should not follow anyone
    real_user = user_manager.create_cognito_only_user('real-uid', 'real')
    assert list(real_user.follow_manager.dynamo.generate_followed_items(real_user.id)) == []
    user_manager.cognito_client.reset_mock()

    # set up our mocks to behave correctly
    user_manager.facebook_client.configure_mock(**{'get_verified_email.return_value': email})
    user_manager.cognito_client.configure_mock(**{
        'create_user_pool_entry.return_value': cognito_token,
    })

    # create the facebook user, check it is as expected
    user = user_manager.create_facebook_user(user_id, username, fb_token, full_name=full_name)
    assert user.id == user_id
    assert user.item['username'] == username
    assert user.item['fullName'] == full_name
    assert user.item['email'] == email.lower()

    # check mocks called as expected
    assert user_manager.facebook_client.mock_calls == [call.get_verified_email(fb_token)]
    assert user_manager.cognito_client.mock_calls == [
        call.create_user_pool_entry(user_id, email.lower(), username),
        call.link_identity_pool_entries(user_id, cognito_id_token=cognito_token, facebook_access_token=fb_token),
    ]

    # check we are following the real user
    followeds = list(user.follow_manager.dynamo.generate_followed_items(user.id))
    assert len(followeds) == 1
    assert followeds[0]['followedUserId'] == real_user.id


def test_create_google_user_success(user_manager):
    google_token = 'google-token'
    cognito_token = 'cog-token'
    user_id = 'my-user-id'
    username = 'therealuser'
    full_name = 'my-full-name'
    email = 'My@email.com'  # emails from google can have upper case characters in them

    # create a 'real' user, they should not follow anyone
    real_user = user_manager.create_cognito_only_user('real-uid', 'real')
    assert list(real_user.follow_manager.dynamo.generate_followed_items(real_user.id)) == []
    user_manager.cognito_client.reset_mock()

    # set up our mocks to behave correctly
    user_manager.google_client.configure_mock(**{'get_verified_email.return_value': email})
    user_manager.cognito_client.configure_mock(**{
        'create_user_pool_entry.return_value': cognito_token,
    })

    # create the google user, check it is as expected
    user = user_manager.create_google_user(user_id, username, google_token, full_name=full_name)
    assert user.id == user_id
    assert user.item['username'] == username
    assert user.item['fullName'] == full_name
    assert user.item['email'] == email.lower()

    # check mocks called as expected
    assert user_manager.google_client.mock_calls == [call.get_verified_email(google_token)]
    assert user_manager.cognito_client.mock_calls == [
        call.create_user_pool_entry(user_id, email.lower(), username),
        call.link_identity_pool_entries(user_id, cognito_id_token=cognito_token, google_id_token=google_token),
    ]

    # check we are following the real user
    followeds = list(user.follow_manager.dynamo.generate_followed_items(user.id))
    assert len(followeds) == 1
    assert followeds[0]['followedUserId'] == real_user.id


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


def test_get_text_tags(user_manager):
    # no tags
    text = 'no tags here'
    assert user_manager.get_text_tags(text) == []

    # with tags, but not of users that exist
    text = 'hey @youDontExist and @meneither'
    assert user_manager.get_text_tags(text) == []

    # create two users in the DB
    user_id1 = 'my-user-id'
    username1 = 'therealuser'
    user_manager.create_cognito_only_user(user_id1, username1)

    user_id2 = 'my-other-id'
    username2 = 'bestUsername'
    user_manager.create_cognito_only_user(user_id2, username2)

    # with tags, some that exist and others that dont
    text = f'hey @{username1} and @nopenope and @{username2}'
    assert sorted(user_manager.get_text_tags(text), key=lambda x: x['tag']) == sorted([
        {'tag': f'@{username1}', 'userId': user_id1},
        {'tag': f'@{username2}', 'userId': user_id2},
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
