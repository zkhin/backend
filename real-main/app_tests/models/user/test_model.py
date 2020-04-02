from unittest.mock import call

import pytest

from app.models.follow.enums import FollowStatus
from app.utils import image_size


@pytest.fixture
def user(user_manager):
    user_id = 'my-user-id'
    username = 'theREALuser'
    user = user_manager.create_cognito_only_user(user_id, username)
    user.cognito_client.reset_mock()
    yield user


@pytest.fixture
def user2(user_manager):
    user_id = 'my-user-id-2'
    username = 'theREALuser2'
    user = user_manager.create_cognito_only_user(user_id, username)
    user.cognito_client.reset_mock()
    yield user


@pytest.fixture
def user3(user_manager):
    user_id = 'my-user-id-3'
    username = 'theREALuser3'
    user = user_manager.create_cognito_only_user(user_id, username)
    user.cognito_client.reset_mock()
    yield user


def test_refresh(user):
    new_username = 'really good'
    assert user.item['username'] != new_username

    # go behind their back and change the DB item on them
    user.dynamo.update_user_username(user.id, new_username, user.item['username'])
    user.refresh_item()
    assert user.item['username'] == new_username


def test_invalid_username(user):
    invalid_username = '-'

    with pytest.raises(user.exceptions.UserValidationException):
        user.update_username(invalid_username)

    assert user.item['username'] != invalid_username
    assert user.cognito_client.mock_calls == []


def test_update_username_no_change(user):
    username = user.item['username']

    org_user_item = user.item
    user_item = user.update_username(username).item
    assert user_item == org_user_item
    assert user.cognito_client.mock_calls == []


def test_success_update_username(user):
    new_username = 'newusername'

    # change the username, verify it changed
    user_item = user.update_username(new_username).item
    assert user_item['username'] == new_username

    # check social calls as expected
    assert user.cognito_client.mock_calls == [
        call.set_user_attributes(user.id, {'preferred_username': new_username}),
    ]


def test_cant_update_username_to_one_already_taken(user, user2):
    username = 'nothingButClearSkies'

    # another user takes the username (case insensitive)
    user2.update_username(username.lower())
    assert user2.item['username'] == username.lower()

    # configure the mocked cognito backend to respond as the real one does
    exception = user.cognito_client.boto_client.exceptions.AliasExistsException({}, None)
    user.cognito_client.configure_mock(**{'set_user_attributes.side_effect': exception})

    # verify we can't update to that username
    with pytest.raises(user.exceptions.UserValidationException):
        user.update_username(username.upper())


def test_update_no_details(user):
    org_user_item = user.item
    user.update_details()
    # check the user_item has not been replaced
    assert user.item is org_user_item


def test_update_with_defaults_causes_no_update(user):
    org_user_item = user.item
    user.update_details(language_code='en', theme_code='black.green')
    # check the user_item has not been replaced
    assert user.item is org_user_item


def test_update_all_details(user):
    # check only privacy status is already set
    assert 'fullName' not in user.item
    assert 'bio' not in user.item
    assert 'languageCode' not in user.item
    assert 'themeCode' not in user.item
    assert 'followCountsHidden' not in user.item
    assert 'viewCountsHidden' not in user.item

    user.update_details(full_name='f', bio='b', language_code='de', theme_code='orange', follow_counts_hidden=True,
                        view_counts_hidden=True)

    # check the user.item has not been replaced
    assert user.item['fullName'] == 'f'
    assert user.item['bio'] == 'b'
    assert user.item['languageCode'] == 'de'
    assert user.item['themeCode'] == 'orange'
    assert user.item['followCountsHidden'] is True
    assert user.item['viewCountsHidden'] is True


def test_delete_all_details(user):
    # set some details
    user.update_details(full_name='f', bio='b', language_code='de', theme_code='orange', follow_counts_hidden=True,
                        view_counts_hidden=True)

    # delete those details, all except for privacyStatus which can't be deleted
    user.update_details(full_name='', bio='', language_code='', theme_code='', follow_counts_hidden=False,
                        view_counts_hidden=False)

    # check the delete made it through
    assert 'fullName' not in user.item
    assert 'bio' not in user.item
    assert 'languageCode' not in user.item
    assert 'themeCode' not in user.item
    assert 'followCountsHidden' not in user.item
    assert 'viewCountsHidden' not in user.item


def test_set_privacy_status_no_change(user):
    privacy_status = user.enums.UserPrivacyStatus.PUBLIC
    user.set_privacy_status(privacy_status)

    org_user_item = user.item
    user.set_privacy_status(privacy_status)
    # verify there was no write to the DB by checking object identity
    assert org_user_item is user.item


def test_set_privacy_status_from_public_to_private(user):
    privacy_status = user.enums.UserPrivacyStatus.PUBLIC
    user.set_privacy_status(privacy_status)
    assert user.item['privacyStatus'] == privacy_status

    privacy_status = user.enums.UserPrivacyStatus.PRIVATE
    user.set_privacy_status(privacy_status)
    assert user.item['privacyStatus'] == privacy_status


def test_set_privacy_status_from_private_to_public(user_manager, user, user2, user3):
    follow_manager = user_manager.follow_manager
    privacy_status = user.enums.UserPrivacyStatus.PRIVATE
    user.set_privacy_status(privacy_status)
    assert user.item['privacyStatus'] == privacy_status

    # set up a follow request in REQUESTED state
    follow_manager.request_to_follow(user2, user)

    # set up a follow request in DENIED state
    follow_manager.request_to_follow(user3, user).deny()

    # check we can see those two request
    resp = list(follow_manager.dynamo.generate_follower_items(user.id, follow_status=FollowStatus.REQUESTED))
    assert len(resp) == 1
    resp = list(follow_manager.dynamo.generate_follower_items(user.id, follow_status=FollowStatus.DENIED))
    assert len(resp) == 1

    # change to private
    privacy_status = user.enums.UserPrivacyStatus.PUBLIC
    user.set_privacy_status(privacy_status)
    assert user.item['privacyStatus'] == privacy_status

    # check those two requests disappeared
    resp = list(follow_manager.dynamo.generate_follower_items(user.id, follow_status=FollowStatus.REQUESTED))
    assert len(resp) == 0
    resp = list(follow_manager.dynamo.generate_follower_items(user.id, follow_status=FollowStatus.DENIED))
    assert len(resp) == 0


def test_start_change_email(user):
    prev_email = 'stop@stop.com'
    user.item = user.dynamo.set_user_details(user.id, email=prev_email)

    new_email = 'go@go.com'
    user.start_change_contact_attribute('email', new_email)
    assert user.item['email'] == prev_email

    assert user.cognito_client.mock_calls == [
        call.set_user_attributes(user.id, {'email': new_email, 'custom:unverified_email': new_email}),
        call.set_user_attributes(user.id, {'email': prev_email, 'email_verified': 'true'}),
    ]


def test_finish_change_email(user):
    new_email = 'go@go.com'
    user.cognito_client.configure_mock(**{
        'get_user_attributes.return_value': {'custom:unverified_email': new_email}
    })

    access_token = {}
    verification_code = {}
    user.finish_change_contact_attribute('email', access_token, verification_code)
    assert user.item['email'] == new_email

    assert user.cognito_client.mock_calls == [
        call.get_user_attributes(user.id),
        call.verify_user_attribute(access_token, 'email', verification_code),
        call.set_user_attributes(user.id, {'email': new_email, 'email_verified': 'true'}),
        call.clear_user_attribute(user.id, 'custom:unverified_email')
    ]


def test_start_change_phone(user):
    prev_phone = '+123'
    user.item = user.dynamo.set_user_details(user.id, phone=prev_phone)

    new_phone = '+567'
    user.start_change_contact_attribute('phone', new_phone)
    assert user.item['phoneNumber'] == prev_phone

    assert user.cognito_client.mock_calls == [
        call.set_user_attributes(user.id, {'phone_number': new_phone, 'custom:unverified_phone': new_phone}),
        call.set_user_attributes(user.id, {'phone_number': prev_phone, 'phone_number_verified': 'true'}),
    ]


def test_finish_change_phone(user):
    new_phone = '+567'
    user.cognito_client.configure_mock(**{
        'get_user_attributes.return_value': {'custom:unverified_phone': new_phone}
    })

    access_token = {}
    verification_code = {}
    user.finish_change_contact_attribute('phone', access_token, verification_code)
    assert user.item['phoneNumber'] == new_phone

    assert user.cognito_client.mock_calls == [
        call.get_user_attributes(user.id),
        call.verify_user_attribute(access_token, 'phone_number', verification_code),
        call.set_user_attributes(user.id, {'phone_number': new_phone, 'phone_number_verified': 'true'}),
        call.clear_user_attribute(user.id, 'custom:unverified_phone')
    ]


def test_start_change_email_same_as_existing(user):
    prev_email = 'stop@stop.com'
    user.item = user.dynamo.set_user_details(user.id, email=prev_email)

    new_email = prev_email
    with pytest.raises(user.exceptions.UserVerificationException):
        user.start_change_contact_attribute('email', new_email)


def test_start_change_email_no_old_value(user):
    new_email = 'go@go.com'
    user.start_change_contact_attribute('email', new_email)
    assert 'email' not in user.item

    assert user.cognito_client.mock_calls == [
        call.set_user_attributes(user.id, {'email': new_email, 'custom:unverified_email': new_email}),
    ]


def test_finish_change_email_no_unverified_email(user):
    user.cognito_client.configure_mock(**{
        'get_user_attributes.return_value': {}
    })

    access_token = {}
    verification_code = {}
    with pytest.raises(user.exceptions.UserVerificationException):
        user.finish_change_contact_attribute('email', access_token, verification_code)
    assert 'email' not in user.item


def test_finish_change_email_wrong_verification_code(user):
    new_email = 'go@go.com'
    exception = user.cognito_client.boto_client.exceptions.CodeMismatchException({}, None)
    user.cognito_client.configure_mock(**{
        'get_user_attributes.return_value': {'custom:unverified_email': new_email},
        'verify_user_attribute.side_effect': exception,
    })

    access_token = {}
    verification_code = {}
    with pytest.raises(user.exceptions.UserVerificationException):
        user.finish_change_contact_attribute('email', access_token, verification_code)
    assert 'email' not in user.item


def test_delete_user_basic_flow(user):
    # delete the user
    org_user_id = user.id
    org_user_item = user.item
    deleted_user_item = user.delete()
    assert deleted_user_item == org_user_item

    # verify cognito was called to release username over there
    assert user.cognito_client.mock_calls == [
        call.clear_user_attribute(org_user_id, 'preferred_username'),
    ]

    # verify it got removed from the db
    resp = user.dynamo.get_user(org_user_id)
    assert resp is None


def test_delete_user_deletes_trending(user):
    trending_manager = user.trending_manager
    user_id = user.id

    # add a trending for the user
    item_type = trending_manager.enums.TrendingItemType.USER
    trending_manager.record_view_count(item_type, user.id, 4)

    # verify we can see it
    resp = trending_manager.dynamo.get_trending(user_id)
    assert resp is not None

    # delete the user
    user.delete()

    # verify the trending has disappeared
    resp = trending_manager.dynamo.get_trending(user_id)
    assert resp is None


def test_delete_user_releases_username(user, user2):
    # release our username by deleting our user
    username = user.item['username']
    user.delete()

    # verify the username is now available by adding it to another
    user2.update_username(username)
    assert user2.item['username'] == username


def test_delete_no_entry_in_user_pool(user, caplog):
    # configure the user pool to behave as if there is no entry for this user
    exception = user.cognito_client.boto_client.exceptions.UserNotFoundException({}, None)
    user.cognito_client.configure_mock(**{'clear_user_attribute.side_effect': exception})

    # verify a delete works as usual
    user_id = user.id
    user.delete()
    assert user.item is None
    assert user.id is None
    assert user.dynamo.get_user(user_id) is None

    # verify the issue was logged
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == 'WARNING'
    assert 'No cognito user pool entry found' in caplog.records[0].msg


def test_delete_user_with_profile_pic(user):
    post_id = 'mid'
    photo_data = b'this is an image'
    content_type = 'image/jpeg'

    # add a profile pic of all sizes for that user
    paths = [user.get_photo_path(size, photo_post_id=post_id) for size in image_size.ALL]
    for path in paths:
        user.s3_uploads_client.put_object(path, photo_data, content_type)
    user.dynamo.set_user_photo_post_id(user.id, post_id)
    user.refresh_item()

    # verify s3 was populated, dynamo set
    for size in image_size.ALL:
        path = user.get_photo_path(size)
        assert user.s3_uploads_client.exists(path)
    assert 'photoPostId' in user.item

    # delete the user
    user.delete()

    # verify the profile pic got removed from s3
    for path in paths:
        assert not user.s3_uploads_client.exists(path)


def test_serailize_self(user):
    resp = user.serialize(user.id)
    assert resp.pop('blockerStatus') == 'SELF'
    assert resp.pop('followedStatus') == 'SELF'
    assert resp == user.item


def test_serailize_unrelated(user, user2):
    resp = user.serialize(user2.id)
    assert resp.pop('blockerStatus') == 'NOT_BLOCKING'
    assert resp.pop('followedStatus') == 'NOT_FOLLOWING'
    assert resp == user.item


def test_serailize_blocker(user, user2, block_manager):
    # they block caller
    block_manager.block(user, user2)
    user.refresh_item()

    resp = user.serialize(user2.id)
    assert resp.pop('blockerStatus') == 'BLOCKING'
    assert resp.pop('followedStatus') == 'NOT_FOLLOWING'
    assert resp == user.item


def test_serailize_followed(user, user2, follow_manager):
    # caller follows them
    follow_manager.request_to_follow(user2, user)
    user.refresh_item()

    resp = user.serialize(user2.id)
    assert resp.pop('blockerStatus') == 'NOT_BLOCKING'
    assert resp.pop('followedStatus') == 'FOLLOWING'
    assert resp == user.item
