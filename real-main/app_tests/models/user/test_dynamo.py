from datetime import datetime

import pytest

from app.models.user.dynamo import UserDynamo
from app.models.user.enums import UserPrivacyStatus
from app.models.user.exceptions import UserDoesNotExist


@pytest.fixture
def user_dynamo(dynamo_client):
    yield UserDynamo(dynamo_client)


def test_add_user_minimal(user_dynamo):
    user_id = 'my-user-id'
    username = 'my-USername'

    before = datetime.utcnow()
    item = user_dynamo.add_user(user_id, username)
    after = datetime.utcnow()

    now = datetime.fromisoformat(item['signedUpAt'][:-1])
    assert before < now
    assert after > now

    assert item == {
        'schemaVersion': 5,
        'partitionKey': f'user/{user_id}',
        'sortKey': 'profile',
        'gsiA1PartitionKey': f'username/{username}',
        'gsiA1SortKey': '-',
        'userId': user_id,
        'username': username,
        'privacyStatus': UserPrivacyStatus.PUBLIC,
        'signedUpAt': now.isoformat() + 'Z',
    }


def test_add_user_maximal(user_dynamo):
    user_id = 'my-user-id'
    username = 'my-USername'
    full_name = 'my-full-name'
    email = 'my-email'
    phone = 'my-phone'
    photo_code = 'red-cat'

    before = datetime.utcnow()
    item = user_dynamo.add_user(user_id, username, full_name=full_name, email=email, phone=phone,
                                placeholder_photo_code=photo_code)
    after = datetime.utcnow()

    now = datetime.fromisoformat(item['signedUpAt'][:-1])
    assert before < now
    assert after > now

    assert item == {
        'schemaVersion': 5,
        'partitionKey': f'user/{user_id}',
        'sortKey': 'profile',
        'gsiA1PartitionKey': f'username/{username}',
        'gsiA1SortKey': '-',
        'userId': user_id,
        'username': username,
        'privacyStatus': UserPrivacyStatus.PUBLIC,
        'signedUpAt': now.isoformat() + 'Z',
        'fullName': full_name,
        'email': email,
        'phoneNumber': phone,
        'placeholderPhotoCode': photo_code,
    }


def test_add_user_at_specific_time(user_dynamo):
    now = datetime.utcnow()
    user_id = 'my-user-id'
    username = 'my-USername'

    item = user_dynamo.add_user(user_id, username, now=now)
    assert item == {
        'schemaVersion': 5,
        'partitionKey': f'user/{user_id}',
        'sortKey': 'profile',
        'gsiA1PartitionKey': f'username/{username}',
        'gsiA1SortKey': '-',
        'userId': user_id,
        'username': username,
        'privacyStatus': UserPrivacyStatus.PUBLIC,
        'signedUpAt': now.isoformat() + 'Z',
    }


def test_get_user_by_username(user_dynamo):
    user_id = 'my-user-id'
    username = 'my-USername'
    user_id2 = 'my-user-id2'
    username2 = 'my-USername2'

    # with nothing in the DB
    assert user_dynamo.get_user_by_username(username) is None

    # add a user, test we can get it and we can miss it
    user_dynamo.add_user(user_id, username)
    assert user_dynamo.get_user_by_username(username2) is None
    assert user_dynamo.get_user_by_username(username)['userId'] == user_id
    assert user_dynamo.get_user_by_username(username)['username'] == username

    # add another user, check we can get them both
    user_dynamo.add_user(user_id2, username2)
    assert user_dynamo.get_user_by_username(username)['userId'] == user_id
    assert user_dynamo.get_user_by_username(username2)['userId'] == user_id2


def test_delete_user(user_dynamo):
    user_id = 'my-user-id'
    username = 'my-USername'

    # add the user to the DB
    item = user_dynamo.add_user(user_id, username)
    assert item['userId'] == user_id

    # do the delete
    resp = user_dynamo.delete_user(user_id)
    assert resp == item

    # check that it was really removed from the db
    resp = user_dynamo.client.get_item(item)
    assert resp is None


def test_update_user_username(user_dynamo):
    user_id = 'my-user-id'
    old_username = 'my-USername'
    new_username = 'better-USername'

    # add user to DB
    old_item = user_dynamo.add_user(user_id, old_username)
    assert old_item['username'] == old_username

    # change their username
    now = datetime.utcnow()
    new_item = user_dynamo.update_user_username(user_id, new_username, old_username, now=now)
    assert new_item['username'] == new_username
    assert new_item['usernameLastValue'] == old_username
    assert datetime.fromisoformat(new_item['usernameLastChangedAt'][:-1]) == now
    assert new_item['gsiA1PartitionKey'] == f'username/{new_username}'
    assert new_item['gsiA1SortKey'] == '-'

    new_item['username'] = old_item['username']
    new_item['gsiA1PartitionKey'] = old_item['gsiA1PartitionKey']
    del new_item['usernameLastValue']
    del new_item['usernameLastChangedAt']
    assert new_item == old_item


def test_set_user_photo_media_id(user_dynamo):
    user_id = 'my-user-id'
    username = 'name'
    media_id = 'mid'

    # add user to DB
    item = user_dynamo.add_user(user_id, username)
    assert item['username'] == username

    # check it starts empty
    item = user_dynamo.get_user(user_id)
    assert 'photoMediaId' not in item

    # set it
    item = user_dynamo.set_user_photo_media_id(user_id, media_id)
    assert item['photoMediaId'] == media_id

    # check that it really made it to the db
    item = user_dynamo.get_user(user_id)
    assert item['photoMediaId'] == media_id


def test_set_user_photo_path_delete_it(user_dynamo):
    user_id = 'my-user-id'
    username = 'name'
    old_media_id = 'mid'

    # add user to DB
    item = user_dynamo.add_user(user_id, username)
    assert item['username'] == username

    # set old media id
    item = user_dynamo.set_user_photo_media_id(user_id, old_media_id)
    assert item['photoMediaId'] == old_media_id

    # set new photo path, deleting it
    item = user_dynamo.set_user_photo_media_id(user_id, None)
    assert 'photoMediaId' not in item

    # check that it really made it to the db
    item = user_dynamo.get_user(user_id)
    assert 'photoMediaId' not in item


def test_set_user_details_doesnt_exist(user_dynamo):
    with pytest.raises(Exception):
        user_dynamo.set_user_details('user-id', full_name='my-full-name')


def test_set_user_details(user_dynamo):
    user_id = 'my-user-id'
    username = 'my-username'

    user_dynamo.add_user('other-id-1', 'noise-1', 'cog-noise-1')
    expected_base_item = user_dynamo.add_user(user_id, username)
    assert expected_base_item['userId'] == user_id
    user_dynamo.add_user('other-id-2', 'noise-2', 'cog-noise-2')

    resp = user_dynamo.set_user_details(user_id, full_name='fn')
    assert resp == {**expected_base_item, **{'fullName': 'fn'}}

    resp = user_dynamo.set_user_details(user_id, full_name='f', bio='b', language_code='l', theme_code='tc',
                                        follow_counts_hidden=True, view_counts_hidden=True,
                                        email='e', phone='p', comments_disabled=True, likes_disabled=True,
                                        sharing_disabled=True, verification_hidden=True)
    expected = {
        **expected_base_item,
        **{
            'fullName': 'f',
            'bio': 'b',
            'languageCode': 'l',
            'themeCode': 'tc',
            'followCountsHidden': True,
            'viewCountsHidden': True,
            'email': 'e',
            'phoneNumber': 'p',
            'commentsDisabled': True,
            'likesDisabled': True,
            'sharingDisabled': True,
            'verificationHidden': True,
        },
    }
    assert resp == expected


def test_set_user_details_delete_all_optional(user_dynamo):
    user_id = 'my-user-id'
    username = 'my-username'

    # create the user
    expected_base_item = user_dynamo.add_user(user_id, username)
    assert expected_base_item['userId'] == user_id

    expected_full_item = {
        **expected_base_item,
        **{
            'fullName': 'f',
            'bio': 'b',
            'languageCode': 'l',
            'themeCode': 'tc',
            'followCountsHidden': True,
            'viewCountsHidden': True,
            'email': 'e',
            'phoneNumber': 'p',
            'commentsDisabled': True,
            'likesDisabled': True,
            'sharingDisabled': True,
            'verificationHidden': True,
        },
    }

    # set all optionals
    resp = user_dynamo.set_user_details(user_id, full_name='f', bio='b', language_code='l', theme_code='tc',
                                        follow_counts_hidden=True, view_counts_hidden=True,
                                        email='e', phone='p', comments_disabled=True, likes_disabled=True,
                                        sharing_disabled=True, verification_hidden=True)
    assert resp == expected_full_item

    # delete all optionals
    resp = user_dynamo.set_user_details(user_id, full_name='', bio='', language_code='', theme_code='',
                                        follow_counts_hidden=False, view_counts_hidden=False,
                                        email='', phone='', comments_disabled=False, likes_disabled=False,
                                        sharing_disabled=False, verification_hidden=False)
    assert resp == expected_base_item


def test_cant_set_privacy_status_to_random_string(user_dynamo):
    with pytest.raises(Exception, match='privacy_status'):
        user_dynamo.set_user_details('user-id', privacy_status='invalid')


def test_set_user_accepted_eula_version(user_dynamo):
    user_id = 'my-user-id'
    username = 'my-username'

    # create the user, verify user starts with no EULA version
    user_item = user_dynamo.add_user(user_id, username)
    assert user_item['userId'] == user_id
    assert 'acceptedEULAVersion' not in user_item

    # set it
    version_1 = '2019-11-14'
    user_item = user_dynamo.set_user_accepted_eula_version(user_id, version_1)
    assert user_item['acceptedEULAVersion'] == version_1

    # set it again
    version_2 = '2019-12-14'
    user_item = user_dynamo.set_user_accepted_eula_version(user_id, version_2)
    assert user_item['acceptedEULAVersion'] == version_2

    # delete it
    user_item = user_dynamo.set_user_accepted_eula_version(user_id, None)
    assert 'acceptedEULAVersion' not in user_item


def test_set_user_privacy_status(user_dynamo):
    user_id = 'my-user-id'
    username = 'my-username'

    # create the user, verify user starts with PUBLIC
    user_item = user_dynamo.add_user(user_id, username)
    assert user_item['userId'] == user_id
    assert user_item['privacyStatus'] == UserPrivacyStatus.PUBLIC

    # set to private
    user_item = user_dynamo.set_user_privacy_status(user_id, UserPrivacyStatus.PRIVATE)
    assert user_item['privacyStatus'] == UserPrivacyStatus.PRIVATE

    # back to public
    user_item = user_dynamo.set_user_privacy_status(user_id, UserPrivacyStatus.PUBLIC)
    assert user_item['privacyStatus'] == UserPrivacyStatus.PUBLIC


def test_increment_decrement_post_count(user_dynamo):
    user_id = 'my-user-id'
    username = 'my-username'

    # create the user, verify user starts with no post count
    user_item = user_dynamo.add_user(user_id, username)
    assert user_item['userId'] == user_id
    assert 'postCount' not in user_item

    # verify can't go below zero
    transacts = [user_dynamo.transact_decrement_post_count(user_id)]
    with pytest.raises(user_dynamo.client.boto3_client.exceptions.ConditionalCheckFailedException):
        user_dynamo.client.transact_write_items(transacts)

    # increment
    transacts = [user_dynamo.transact_increment_post_count(user_id)]
    user_dynamo.client.transact_write_items(transacts)
    user_item = user_dynamo.get_user(user_id)
    assert user_item['postCount'] == 1

    # decrement
    transacts = [user_dynamo.transact_decrement_post_count(user_id)]
    user_dynamo.client.transact_write_items(transacts)
    user_item = user_dynamo.get_user(user_id)
    assert user_item['postCount'] == 0


def test_increment_decrement_follower_count(user_dynamo):
    user_id = 'my-user-id'
    username = 'my-username'

    # create the user, verify user starts with no follower count
    user_item = user_dynamo.add_user(user_id, username)
    assert user_item['userId'] == user_id
    assert 'followerCount' not in user_item

    # verify can't go below zero
    transacts = [user_dynamo.transact_decrement_follower_count(user_id)]
    with pytest.raises(user_dynamo.client.boto3_client.exceptions.ConditionalCheckFailedException):
        user_dynamo.client.transact_write_items(transacts)

    # increment
    transacts = [user_dynamo.transact_increment_follower_count(user_id)]
    user_dynamo.client.transact_write_items(transacts)
    user_item = user_dynamo.get_user(user_id)
    assert user_item['followerCount'] == 1

    # decrement
    transacts = [user_dynamo.transact_decrement_follower_count(user_id)]
    user_dynamo.client.transact_write_items(transacts)
    user_item = user_dynamo.get_user(user_id)
    assert user_item['followerCount'] == 0


def test_increment_decrement_followed_count(user_dynamo):
    user_id = 'my-user-id'
    username = 'my-username'

    # create the user, verify user starts with no followed count
    user_item = user_dynamo.add_user(user_id, username)
    assert user_item['userId'] == user_id
    assert 'followedCount' not in user_item

    # verify can't go below zero
    transacts = [user_dynamo.transact_decrement_followed_count(user_id)]
    with pytest.raises(user_dynamo.client.boto3_client.exceptions.ConditionalCheckFailedException):
        user_dynamo.client.transact_write_items(transacts)

    # increment
    transacts = [user_dynamo.transact_increment_followed_count(user_id)]
    user_dynamo.client.transact_write_items(transacts)
    user_item = user_dynamo.get_user(user_id)
    assert user_item['followedCount'] == 1

    # decrement
    transacts = [user_dynamo.transact_decrement_followed_count(user_id)]
    user_dynamo.client.transact_write_items(transacts)
    user_item = user_dynamo.get_user(user_id)
    assert user_item['followedCount'] == 0


def test_increment_decrement_album_count(user_dynamo):
    user_id = 'my-user-id'
    username = 'my-username'

    # create the user, verify user starts with no album count
    user_item = user_dynamo.add_user(user_id, username)
    assert user_item['userId'] == user_id
    assert 'albumCount' not in user_item

    # verify can't go below zero
    transacts = [user_dynamo.transact_decrement_album_count(user_id)]
    with pytest.raises(user_dynamo.client.boto3_client.exceptions.ConditionalCheckFailedException):
        user_dynamo.client.transact_write_items(transacts)

    # increment
    transacts = [user_dynamo.transact_increment_album_count(user_id)]
    user_dynamo.client.transact_write_items(transacts)
    user_item = user_dynamo.get_user(user_id)
    assert user_item['albumCount'] == 1

    # decrement
    transacts = [user_dynamo.transact_decrement_album_count(user_id)]
    user_dynamo.client.transact_write_items(transacts)
    user_item = user_dynamo.get_user(user_id)
    assert user_item['albumCount'] == 0


def test_increment_post_viewed_by_count_doesnt_exist(user_dynamo):
    user_id = 'doesnt-exist'
    with pytest.raises(UserDoesNotExist):
        user_dynamo.increment_post_viewed_by_count(user_id)


def test_increment_user_post_viewed_by_count(user_dynamo):
    # create a user
    user_id = 'user-id'
    user_item = user_dynamo.add_user(user_id, 'username')
    assert user_item['userId'] == user_id
    assert user_item.get('postViewedByCount', 0) == 0

    # verify it has no view count
    user_item = user_dynamo.get_user(user_id)
    assert user_item['userId'] == user_id
    assert user_item.get('postViewedByCount', 0) == 0

    # record a view
    user_item = user_dynamo.increment_post_viewed_by_count(user_id)
    assert user_item['userId'] == user_id
    assert user_item['postViewedByCount'] == 1

    # verify it really got the view count
    user_item = user_dynamo.get_user(user_id)
    assert user_item['userId'] == user_id
    assert user_item['postViewedByCount'] == 1

    # record some more views
    user_item = user_dynamo.increment_post_viewed_by_count(user_id)
    assert user_item['userId'] == user_id
    assert user_item['postViewedByCount'] == 2

    # verify it really got the view count
    user_item = user_dynamo.get_user(user_id)
    assert user_item['userId'] == user_id
    assert user_item['postViewedByCount'] == 2
