import unittest.mock as mock
import uuid

import pytest

from app.models.follow.enums import FollowStatus
from app.models.user.enums import UserStatus
from app.utils import image_size


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def user2(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def user3(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


@pytest.fixture
def user_verified_phone(user_manager, cognito_client):
    user_id, username = str(uuid.uuid4()), str(uuid.uuid4())[:8]
    phone = '+12125551212'
    cognito_client.boto_client.admin_create_user(
        UserPoolId=cognito_client.user_pool_id,
        Username=user_id,
        MessageAction='SUPPRESS',
        UserAttributes=[{
            'Name': 'phone_number',
            'Value': phone,
        }, {
            'Name': 'phone_number_verified',
            'Value': 'true',
        }, {
            'Name': 'preferred_username',
            'Value': username.lower(),
        }],
    )
    yield user_manager.create_cognito_only_user(user_id, username)


def test_refresh(user):
    new_username = 'really good'
    assert user.item['username'] != new_username

    # go behind their back and change the DB item on them
    user.dynamo.update_user_username(user.id, new_username, user.item['username'])
    user.refresh_item()
    assert user.item['username'] == new_username


def test_invalid_username(user):
    user.cognito_client = mock.Mock()

    invalid_username = '-'
    with pytest.raises(user.exceptions.UserValidationException):
        user.update_username(invalid_username)

    assert user.item['username'] != invalid_username
    assert user.cognito_client.mock_calls == []


def test_update_username_no_change(user):
    user.cognito_client = mock.Mock()

    org_user_item = user.item
    user.update_username(user.username)
    assert user.item == org_user_item
    assert user.cognito_client.mock_calls == []


def test_success_update_username(user):
    assert user.cognito_client.get_user_attributes(user.id)['preferred_username'] == user.username.lower()

    # change the username, verify it changed
    new_username = user.username + 'newusername'
    user.update_username(new_username)
    assert user.username == new_username
    assert user.cognito_client.get_user_attributes(user.id)['preferred_username'] == new_username.lower()


def test_cant_update_username_to_one_already_taken(user, user2):
    username = 'nothingButClearSkies'

    # another user takes the username (case insensitive)
    user2.update_username(username.lower())
    assert user2.item['username'] == username.lower()

    # mock out the cognito backend so it behaves like the real thing
    exception = user.cognito_client.boto_client.exceptions.AliasExistsException({}, None)
    user.cognito_client.set_user_attributes = mock.Mock(side_effect=exception)

    # verify we can't update to that username
    with pytest.raises(user.exceptions.UserValidationException):
        user.update_username(username.upper())


def test_update_no_details(user):
    org_user_item = user.item
    user.update_details()
    # check the user_item has not been replaced
    assert user.item is org_user_item


def test_update_with_existing_values_causes_no_update(user):
    user.update_details(language_code='en', likes_disabled=False)
    assert user.item['languageCode'] == 'en'
    assert user.item['likesDisabled'] is False
    assert 'fullName' not in user.item
    org_user_item = user.item
    user.update_details(language_code='en', likes_disabled=False, full_name='')
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
    user.update_details(full_name='', bio='', language_code='', theme_code='', follow_counts_hidden='',
                        view_counts_hidden='')

    # check the delete made it through
    assert 'fullName' not in user.item
    assert 'bio' not in user.item
    assert 'languageCode' not in user.item
    assert 'themeCode' not in user.item
    assert 'followCountsHidden' not in user.item
    assert 'viewCountsHidden' not in user.item


def test_get_set_user_status(user):
    assert user.status == UserStatus.ACTIVE
    assert 'userStatus' not in user.item

    # no op
    user.set_user_status(UserStatus.ACTIVE)
    assert user.status == UserStatus.ACTIVE

    # change it
    user.set_user_status(UserStatus.DELETING)
    assert user.status == UserStatus.DELETING
    assert user.item['userStatus'] == UserStatus.DELETING

    # change it again
    user.set_user_status(UserStatus.DISABLED)
    assert user.status == UserStatus.DISABLED

    # change it back
    user.set_user_status(UserStatus.ACTIVE)
    assert user.status == UserStatus.ACTIVE


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
    user.cognito_client.set_user_attributes(user.id, {'email': prev_email, 'email_verified': 'true'})

    # check starting state
    user.item['email'] == prev_email
    attrs = user.cognito_client.get_user_attributes(user.id)
    assert attrs['email'] == prev_email
    assert attrs['email_verified'] == 'true'
    assert 'custom:unverified_email' not in attrs

    # start the email change
    new_email = 'go@go.com'
    user.start_change_contact_attribute('email', new_email)

    # check final state
    assert user.item['email'] == prev_email
    attrs = user.cognito_client.get_user_attributes(user.id)
    assert attrs['email'] == prev_email
    assert attrs['email_verified'] == 'true'
    assert attrs['custom:unverified_email'] == new_email


def test_finish_change_email(user):
    # set up cognito like we have already started an email change
    new_email = 'go@go.com'
    user.cognito_client.set_user_attributes(user.id, {'custom:unverified_email': new_email})

    # moto has not yet implemented verify_user_attribute or admin_delete_user_attributes
    user.cognito_client.verify_user_attribute = mock.Mock()
    user.cognito_client.clear_user_attribute = mock.Mock()

    user.finish_change_contact_attribute('email', 'access_token', 'verification_code')
    assert user.item['email'] == new_email

    attrs = user.cognito_client.get_user_attributes(user.id)
    assert attrs['email'] == new_email
    assert attrs['email_verified'] == 'true'

    assert user.cognito_client.verify_user_attribute.mock_calls == [
        mock.call('access_token', 'email', 'verification_code'),
    ]
    assert user.cognito_client.clear_user_attribute.mock_calls == [mock.call(user.id, 'custom:unverified_email')]


def test_start_change_phone(user):
    prev_phone = '+123'
    user.item = user.dynamo.set_user_details(user.id, phone=prev_phone)
    user.cognito_client.set_user_attributes(user.id, {'phone': prev_phone, 'phone_verified': 'true'})

    # check starting state
    user.item['phoneNumber'] == prev_phone
    attrs = user.cognito_client.get_user_attributes(user.id)
    assert attrs['phone'] == prev_phone
    assert attrs['phone_verified'] == 'true'
    assert 'custom:unverified_phone' not in attrs

    # start the email change
    new_phone = '+567'
    user.start_change_contact_attribute('phone', new_phone)

    # check final state
    assert user.item['phoneNumber'] == prev_phone
    attrs = user.cognito_client.get_user_attributes(user.id)
    assert attrs['phone'] == prev_phone
    assert attrs['phone_verified'] == 'true'
    assert attrs['custom:unverified_phone'] == new_phone


def test_finish_change_phone(user):
    # set attributes in cognito that would have been set when email change process started
    new_phone = '+567'
    user.cognito_client.set_user_attributes(user.id, {'custom:unverified_phone': new_phone})

    # moto has not yet implemented verify_user_attribute or admin_delete_user_attributes
    user.cognito_client.verify_user_attribute = mock.Mock()
    user.cognito_client.clear_user_attribute = mock.Mock()

    user.finish_change_contact_attribute('phone', 'access_token', 'verification_code')
    assert user.item['phoneNumber'] == new_phone

    attrs = user.cognito_client.get_user_attributes(user.id)
    assert attrs['phone_number'] == new_phone
    assert attrs['phone_number_verified'] == 'true'

    assert user.cognito_client.verify_user_attribute.mock_calls == [
        mock.call('access_token', 'phone_number', 'verification_code'),
    ]
    assert user.cognito_client.clear_user_attribute.mock_calls == [mock.call(user.id, 'custom:unverified_phone')]


def test_start_change_email_same_as_existing(user):
    prev_email = 'stop@stop.com'
    user.item = user.dynamo.set_user_details(user.id, email=prev_email)

    new_email = prev_email
    with pytest.raises(user.exceptions.UserVerificationException):
        user.start_change_contact_attribute('email', new_email)


def test_start_change_email_no_old_value(user_verified_phone):
    user = user_verified_phone

    # check starting state
    assert 'email' not in user.item
    user_attrs = user.cognito_client.get_user_attributes(user.id)
    assert 'email' not in user_attrs
    assert 'custom:unverified_email' not in user_attrs

    new_email = 'go@go.com'
    user.start_change_contact_attribute('email', new_email)
    assert 'email' not in user.item

    # check the cognito attributes set correctly
    user_attrs = user.cognito_client.get_user_attributes(user.id)
    assert user_attrs['email'] == new_email
    assert user_attrs['custom:unverified_email'] == new_email


def test_finish_change_email_no_unverified_email(user):
    org_email = user.item['email']
    access_token = {}
    verification_code = {}
    with pytest.raises(user.exceptions.UserVerificationException):
        user.finish_change_contact_attribute('email', access_token, verification_code)
    assert user.cognito_client.get_user_attributes(user.id)['email'] == org_email
    assert user.item['email'] == org_email


def test_finish_change_email_wrong_verification_code(user):
    # set attributes in cognito that would have been set when email change process started
    new_email = 'go@go.com'
    org_email = user.item['email']
    user.cognito_client.set_user_attributes(user.id, {'custom:unverified_email': new_email})

    # moto has not yet implemented verify_user_attribute
    exception = user.cognito_client.boto_client.exceptions.CodeMismatchException({}, None)
    user.cognito_client.boto_client.verify_user_attribute = mock.Mock(side_effect=exception)

    access_token = {}
    verification_code = {}
    with pytest.raises(user.exceptions.UserVerificationException):
        user.finish_change_contact_attribute('email', access_token, verification_code)
    assert user.cognito_client.get_user_attributes(user.id)['email'] == org_email
    assert user.item['email'] == org_email


def test_delete_user_basic_flow(user):
    # moto cognito has not yet implemented admin_delete_user_attributes
    user.cognito_client.clear_user_attribute = mock.Mock()

    # delete the user
    org_user_id = user.id
    org_user_item = user.item
    deleted_user_item = user.delete()
    assert deleted_user_item == org_user_item

    # verify cognito was called to release username over there
    assert user.cognito_client.clear_user_attribute.mock_calls == [
        mock.call(org_user_id, 'preferred_username'),
    ]

    # verify it got removed from the db
    resp = user.dynamo.get_user(org_user_id)
    assert resp is None


def test_delete_user_deletes_trending(user):
    trending_manager = user.trending_manager
    user_id = user.id

    # add a trending for the user
    item_type = trending_manager.enums.TrendingItemType.USER
    trending_manager.increment_score(item_type, user.id)

    # verify we can see it
    resp = trending_manager.dynamo.get_trending(user_id)
    assert resp is not None

    # moto cognito has not yet implemented admin_delete_user_attributes
    user.cognito_client.boto_client.admin_delete_user_attributes = mock.Mock()

    # delete the user
    user.delete()

    # verify the trending has disappeared
    resp = trending_manager.dynamo.get_trending(user_id)
    assert resp is None


def test_delete_user_releases_username(user, user2):
    # moto cognito has not yet implemented admin_delete_user_attributes
    user.cognito_client.boto_client.admin_delete_user_attributes = mock.Mock()

    # release our username by deleting our user
    username = user.item['username']
    user.delete()

    # verify the username is now available by adding it to another
    user2.update_username(username)
    assert user2.item['username'] == username


def test_delete_no_entry_in_user_pool(user, caplog):
    # configure the user pool to behave as if there is no entry for this user
    # note that moto cognito has not yet implemented admin_delete_user_attributes
    exception = user.cognito_client.boto_client.exceptions.UserNotFoundException({}, None)
    user.cognito_client.clear_user_attribute = mock.Mock(side_effect=exception)

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
    paths = [user.get_photo_path(size, photo_post_id=post_id) for size in image_size.JPEGS]
    for path in paths:
        user.s3_uploads_client.put_object(path, photo_data, content_type)
    user.dynamo.set_user_photo_post_id(user.id, post_id)
    user.refresh_item()

    # verify s3 was populated, dynamo set
    for size in image_size.JPEGS:
        path = user.get_photo_path(size)
        assert user.s3_uploads_client.exists(path)
    assert 'photoPostId' in user.item

    # moto cognito has not yet implemented admin_delete_user_attributes
    user.cognito_client.boto_client.admin_delete_user_attributes = mock.Mock()

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


def test_is_forced_disabling_criteria_met_by_posts(user):
    # check starting state
    assert user.item.get('postCount', 0) == 0
    assert user.item.get('postArchivedCount', 0) == 0
    assert user.item.get('postForcedArchivingCount', 0) == 0
    assert user.is_forced_disabling_criteria_met_by_posts() is False

    # first post was force-disabled, shouldn't disable the user
    user.item['postCount'] = 1
    user.item['postArchivedCount'] = 0
    user.item['postForcedArchivingCount'] = 1
    assert user.is_forced_disabling_criteria_met_by_posts() is False

    # just below criteria cutoff
    user.item['postCount'] = 5
    user.item['postArchivedCount'] = 0
    user.item['postForcedArchivingCount'] = 1
    assert user.is_forced_disabling_criteria_met_by_posts() is False
    user.item['postCount'] = 3
    user.item['postArchivedCount'] = 3
    user.item['postForcedArchivingCount'] = 0
    assert user.is_forced_disabling_criteria_met_by_posts() is False

    # just above criteria cutoff
    user.item['postCount'] = 6
    user.item['postArchivedCount'] = 0
    user.item['postForcedArchivingCount'] = 1
    assert user.is_forced_disabling_criteria_met_by_posts() is True
    user.item['postCount'] = 0
    user.item['postArchivedCount'] = 6
    user.item['postForcedArchivingCount'] = 1
    assert user.is_forced_disabling_criteria_met_by_posts() is True
    user.item['postCount'] = 2
    user.item['postArchivedCount'] = 4
    user.item['postForcedArchivingCount'] = 1
    assert user.is_forced_disabling_criteria_met_by_posts() is True


def test_is_forced_disabling_criteria_met_by_comments(user):
    # check starting state
    assert user.item.get('commentCount', 0) == 0
    assert user.item.get('commentDeletedCount', 0) == 0
    assert user.item.get('commentForcedDeletionCount', 0) == 0
    assert user.is_forced_disabling_criteria_met_by_comments() is False

    # first comment was force-disabled, shouldn't disable the user
    user.item['commentCount'] = 1
    user.item['commentDeletedCount'] = 0
    user.item['commentForcedDeletionCount'] = 1
    assert user.is_forced_disabling_criteria_met_by_comments() is False

    # just below criteria cutoff
    user.item['commentCount'] = 5
    user.item['commentDeletedCount'] = 0
    user.item['commentForcedDeletionCount'] = 1
    assert user.is_forced_disabling_criteria_met_by_comments() is False
    user.item['commentCount'] = 3
    user.item['commentDeletedCount'] = 3
    user.item['commentForcedDeletionCount'] = 0
    assert user.is_forced_disabling_criteria_met_by_comments() is False

    # just above criteria cutoff
    user.item['commentCount'] = 6
    user.item['commentDeletedCount'] = 0
    user.item['commentForcedDeletionCount'] = 1
    assert user.is_forced_disabling_criteria_met_by_comments() is True
    user.item['commentCount'] = 0
    user.item['commentDeletedCount'] = 6
    user.item['commentForcedDeletionCount'] = 1
    assert user.is_forced_disabling_criteria_met_by_comments() is True
    user.item['commentCount'] = 2
    user.item['commentDeletedCount'] = 4
    user.item['commentForcedDeletionCount'] = 1
    assert user.is_forced_disabling_criteria_met_by_comments() is True


def test_set_user_accepted_eula_version(user):
    assert 'acceptedEULAVersion' not in user.item

    # set it
    user.set_accepted_eula_version('version-1')
    assert user.item['acceptedEULAVersion'] == 'version-1'
    assert user.refresh_item().item['acceptedEULAVersion'] == 'version-1'

    # no-op set it to same value
    org_item = user.item
    user.set_accepted_eula_version('version-1')
    assert user.item is org_item
    assert user.refresh_item().item['acceptedEULAVersion'] == 'version-1'

    # change value
    user.set_accepted_eula_version('version-2')
    assert user.item['acceptedEULAVersion'] == 'version-2'
    assert user.refresh_item().item['acceptedEULAVersion'] == 'version-2'

    # delete value
    user.set_accepted_eula_version(None)
    assert 'acceptedEULAVersion' not in user.item
    assert 'acceptedEULAVersion' not in user.refresh_item().item

    # no-op delete
    org_item = user.item
    user.set_accepted_eula_version(None)
    assert user.item is org_item
    assert 'acceptedEULAVersion' not in user.refresh_item().item


def test_set_apns_token(user):
    assert 'apnsToken' not in user.item

    # set it
    user.set_apns_token('token-1')
    assert user.item['apnsToken'] == 'token-1'
    assert user.refresh_item().item['apnsToken'] == 'token-1'

    # no-op set it to same value
    org_item = user.item
    user.set_apns_token('token-1')
    assert user.item is org_item
    assert user.refresh_item().item['apnsToken'] == 'token-1'

    # change value
    user.set_apns_token('token-2')
    assert user.item['apnsToken'] == 'token-2'
    assert user.refresh_item().item['apnsToken'] == 'token-2'

    # delete value
    user.set_apns_token(None)
    assert 'apnsToken' not in user.item
    assert 'apnsToken' not in user.refresh_item().item

    # no-op delete
    org_item = user.item
    user.set_apns_token(None)
    assert user.item is org_item
    assert 'apnsToken' not in user.refresh_item().item
