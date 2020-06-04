import pendulum
import pytest

from app.models.post.enums import PostStatus
from app.models.user.dynamo import UserDynamo
from app.models.user.enums import UserPrivacyStatus, UserStatus
from app.models.user.exceptions import UserAlreadyExists, UserDoesNotExist


@pytest.fixture
def user_dynamo(dynamo_client):
    yield UserDynamo(dynamo_client)


def test_add_user_minimal(user_dynamo):
    user_id = 'my-user-id'
    username = 'my-USername'

    before = pendulum.now('utc')
    item = user_dynamo.add_user(user_id, username)
    after = pendulum.now('utc')

    now = pendulum.parse(item['signedUpAt'])
    assert before < now
    assert after > now

    assert item == {
        'schemaVersion': 9,
        'partitionKey': f'user/{user_id}',
        'sortKey': 'profile',
        'gsiA1PartitionKey': f'username/{username}',
        'gsiA1SortKey': '-',
        'userId': user_id,
        'username': username,
        'privacyStatus': UserPrivacyStatus.PUBLIC,
        'signedUpAt': now.to_iso8601_string(),
    }


def test_add_user_maximal(user_dynamo):
    user_id = 'my-user-id'
    username = 'my-USername'
    full_name = 'my-full-name'
    email = 'my-email'
    phone = 'my-phone'
    photo_code = 'red-cat'

    before = pendulum.now('utc')
    item = user_dynamo.add_user(
        user_id, username, full_name=full_name, email=email, phone=phone, placeholder_photo_code=photo_code
    )
    after = pendulum.now('utc')

    now = pendulum.parse(item['signedUpAt'])
    print(item['signedUpAt'])
    print(now)
    print(now.to_iso8601_string())
    assert before < now
    assert after > now

    assert item == {
        'schemaVersion': 9,
        'partitionKey': f'user/{user_id}',
        'sortKey': 'profile',
        'gsiA1PartitionKey': f'username/{username}',
        'gsiA1SortKey': '-',
        'userId': user_id,
        'username': username,
        'privacyStatus': UserPrivacyStatus.PUBLIC,
        'signedUpAt': now.to_iso8601_string(),
        'fullName': full_name,
        'email': email,
        'phoneNumber': phone,
        'placeholderPhotoCode': photo_code,
    }


def test_add_user_already_exists(user_dynamo):
    user_id = 'my-user-id'

    # add the user
    user_dynamo.add_user(user_id, 'bestusername')
    assert user_dynamo.get_user(user_id)['userId'] == user_id

    # verify we can't add them again
    with pytest.raises(UserAlreadyExists):
        user_dynamo.add_user(user_id, 'diffusername')


def test_add_user_at_specific_time(user_dynamo):
    now = pendulum.now('utc')
    user_id = 'my-user-id'
    username = 'my-USername'

    item = user_dynamo.add_user(user_id, username, now=now)
    assert item == {
        'schemaVersion': 9,
        'partitionKey': f'user/{user_id}',
        'sortKey': 'profile',
        'gsiA1PartitionKey': f'username/{username}',
        'gsiA1SortKey': '-',
        'userId': user_id,
        'username': username,
        'privacyStatus': UserPrivacyStatus.PUBLIC,
        'signedUpAt': now.to_iso8601_string(),
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
    now = pendulum.now('utc')
    new_item = user_dynamo.update_user_username(user_id, new_username, old_username, now=now)
    assert new_item['username'] == new_username
    assert new_item['usernameLastValue'] == old_username
    assert pendulum.parse(new_item['usernameLastChangedAt']) == now
    assert new_item['gsiA1PartitionKey'] == f'username/{new_username}'
    assert new_item['gsiA1SortKey'] == '-'

    new_item['username'] = old_item['username']
    new_item['gsiA1PartitionKey'] = old_item['gsiA1PartitionKey']
    del new_item['usernameLastValue']
    del new_item['usernameLastChangedAt']
    assert new_item == old_item


def test_set_user_photo_post_id(user_dynamo):
    user_id = 'my-user-id'
    username = 'name'
    post_id = 'mid'

    # add user to DB
    item = user_dynamo.add_user(user_id, username)
    assert item['username'] == username

    # check it starts empty
    item = user_dynamo.get_user(user_id)
    assert 'photoPostId' not in item

    # set it
    item = user_dynamo.set_user_photo_post_id(user_id, post_id)
    assert item['photoPostId'] == post_id

    # check that it really made it to the db
    item = user_dynamo.get_user(user_id)
    assert item['photoPostId'] == post_id


def test_set_user_photo_path_delete_it(user_dynamo):
    user_id = 'my-user-id'
    username = 'name'
    old_post_id = 'mid'

    # add user to DB
    item = user_dynamo.add_user(user_id, username)
    assert item['username'] == username

    # set old post id
    item = user_dynamo.set_user_photo_post_id(user_id, old_post_id)
    assert item['photoPostId'] == old_post_id

    # set new photo path, deleting it
    item = user_dynamo.set_user_photo_post_id(user_id, None)
    assert 'photoPostId' not in item

    # check that it really made it to the db
    item = user_dynamo.get_user(user_id)
    assert 'photoPostId' not in item


def test_set_user_details_doesnt_exist(user_dynamo):
    with pytest.raises(user_dynamo.client.exceptions.ConditionalCheckFailedException):
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

    resp = user_dynamo.set_user_details(
        user_id,
        full_name='f',
        bio='b',
        language_code='l',
        theme_code='tc',
        follow_counts_hidden=True,
        view_counts_hidden=True,
        email='e',
        phone='p',
        comments_disabled=True,
        likes_disabled=True,
        sharing_disabled=True,
        verification_hidden=True,
    )
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


def test_set_user_details_delete_for_empty_string(user_dynamo):
    user_id = 'my-user-id'
    username = 'my-username'

    # create the user
    expected_base_item = user_dynamo.add_user(user_id, username)
    assert expected_base_item['userId'] == user_id

    # set all optionals
    resp = user_dynamo.set_user_details(
        user_id,
        full_name='f',
        bio='b',
        language_code='l',
        theme_code='tc',
        follow_counts_hidden=True,
        view_counts_hidden=True,
        email='e',
        phone='p',
        comments_disabled=True,
        likes_disabled=True,
        sharing_disabled=True,
        verification_hidden=True,
    )
    assert resp == {
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

    # False does not mean delete anymore
    resp = user_dynamo.set_user_details(
        user_id,
        follow_counts_hidden=False,
        view_counts_hidden=False,
        comments_disabled=False,
        likes_disabled=False,
        sharing_disabled=False,
        verification_hidden=False,
    )
    assert resp == {
        **expected_base_item,
        **{
            'fullName': 'f',
            'bio': 'b',
            'languageCode': 'l',
            'themeCode': 'tc',
            'followCountsHidden': False,
            'viewCountsHidden': False,
            'email': 'e',
            'phoneNumber': 'p',
            'commentsDisabled': False,
            'likesDisabled': False,
            'sharingDisabled': False,
            'verificationHidden': False,
        },
    }

    # empty string means delete
    resp = user_dynamo.set_user_details(
        user_id,
        full_name='',
        bio='',
        language_code='',
        theme_code='',
        follow_counts_hidden='',
        view_counts_hidden='',
        email='',
        phone='',
        comments_disabled='',
        likes_disabled='',
        sharing_disabled='',
        verification_hidden='',
    )
    assert resp == expected_base_item


def test_cant_set_privacy_status_to_random_string(user_dynamo):
    with pytest.raises(AssertionError, match='privacy_status'):
        user_dynamo.set_user_privacy_status('user-id', privacy_status='invalid')


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


def test_set_user_status(user_dynamo):
    # create the user, verify user starts as ACTIVE as default
    user_id = 'my-user-id'
    user_item = user_dynamo.add_user(user_id, 'thebestuser')
    assert user_item['userId'] == user_id
    assert 'userStatus' not in user_item
    assert 'lastDisabledAt' not in user_item

    # can't set it to an invalid value
    with pytest.raises(AssertionError, match='Invalid UserStatus'):
        user_dynamo.set_user_status(user_id, 'nopenope')

    # set it, check
    item = user_dynamo.set_user_status(user_id, UserStatus.DELETING)
    assert item['userStatus'] == UserStatus.DELETING
    assert 'lastDisabledAt' not in item

    # set it to DISABLED, check
    now = pendulum.now('utc')
    item = user_dynamo.set_user_status(user_id, UserStatus.DISABLED, now=now)
    assert item['userStatus'] == UserStatus.DISABLED
    assert item['lastDisabledAt'] == now.to_iso8601_string()

    # double check our writes really have been saving in the DB
    item = user_dynamo.get_user(user_id)
    assert item['userStatus'] == UserStatus.DISABLED
    assert item['lastDisabledAt'] == now.to_iso8601_string()

    # set it to DISABLED again, check
    item = user_dynamo.set_user_status(user_id, UserStatus.DISABLED)
    assert item['userStatus'] == UserStatus.DISABLED
    last_disabled_at = pendulum.parse(item['lastDisabledAt'])
    assert last_disabled_at > now

    # set it to the default, check
    item = user_dynamo.set_user_status(user_id, UserStatus.ACTIVE)
    assert 'userStatus' not in item
    assert item['lastDisabledAt'] == last_disabled_at.to_iso8601_string()


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


def test_increment_decrement_follower_count(user_dynamo):
    user_id = 'my-user-id'
    username = 'my-username'

    # create the user, verify user starts with no follower count
    user_item = user_dynamo.add_user(user_id, username)
    assert user_item['userId'] == user_id
    assert 'followerCount' not in user_item

    # verify can't go below zero
    transacts = [user_dynamo.transact_decrement_follower_count(user_id)]
    with pytest.raises(user_dynamo.client.exceptions.TransactionCanceledException):
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
    with pytest.raises(user_dynamo.client.exceptions.TransactionCanceledException):
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
    with pytest.raises(user_dynamo.client.exceptions.TransactionCanceledException):
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


def test_increment_decrement_chat_count(user_dynamo):
    user_id = 'my-user-id'
    username = 'my-username'

    # create the user, verify user starts with no chat count
    user_item = user_dynamo.add_user(user_id, username)
    assert user_item['userId'] == user_id
    assert 'chatCount' not in user_item

    # verify can't go below zero
    transacts = [user_dynamo.transact_decrement_chat_count(user_id)]
    with pytest.raises(user_dynamo.client.exceptions.TransactionCanceledException):
        user_dynamo.client.transact_write_items(transacts)

    # increment
    transacts = [user_dynamo.transact_increment_chat_count(user_id)]
    user_dynamo.client.transact_write_items(transacts)
    user_item = user_dynamo.get_user(user_id)
    assert user_item['chatCount'] == 1

    # decrement
    transacts = [user_dynamo.transact_decrement_chat_count(user_id)]
    user_dynamo.client.transact_write_items(transacts)
    user_item = user_dynamo.get_user(user_id)
    assert user_item['chatCount'] == 0


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


def test_transact_post_completed(user_dynamo):
    # set up & verify starting state
    user_id = 'user-id'
    user_item = user_dynamo.add_user(user_id, 'username')
    assert user_item['userId'] == user_id
    assert user_item.get('postCount', 0) == 0

    user_dynamo.client.transact_write_items([user_dynamo.transact_post_completed(user_id)])
    user_item = user_dynamo.get_user(user_id)
    assert user_item.get('postCount', 0) == 1

    user_dynamo.client.transact_write_items([user_dynamo.transact_post_completed(user_id)])
    user_item = user_dynamo.get_user(user_id)
    assert user_item.get('postCount', 0) == 2


def test_transact_post_archived(user_dynamo):
    # set up & verify starting state
    user_id = 'user-id'
    user_dynamo.add_user(user_id, 'username')
    user_dynamo.client.transact_write_items([user_dynamo.transact_post_completed(user_id)])
    user_dynamo.client.transact_write_items([user_dynamo.transact_post_completed(user_id)])
    user_dynamo.client.transact_write_items([user_dynamo.transact_post_completed(user_id)])
    user_item = user_dynamo.get_user(user_id)
    assert user_item['userId'] == user_id
    assert user_item.get('postCount', 0) == 3
    assert user_item.get('postArchivedCount', 0) == 0
    assert user_item.get('postForcedArchivingCount', 0) == 0

    # force archive
    user_dynamo.client.transact_write_items([user_dynamo.transact_post_archived(user_id, forced=True)])
    user_item = user_dynamo.get_user(user_id)
    assert user_item.get('postCount', 0) == 2
    assert user_item.get('postArchivedCount', 0) == 1
    assert user_item.get('postForcedArchivingCount', 0) == 1

    # non-force archive
    user_dynamo.client.transact_write_items([user_dynamo.transact_post_archived(user_id)])
    user_item = user_dynamo.get_user(user_id)
    assert user_item.get('postCount', 0) == 1
    assert user_item.get('postArchivedCount', 0) == 2
    assert user_item.get('postForcedArchivingCount', 0) == 1

    # force archive
    user_dynamo.client.transact_write_items([user_dynamo.transact_post_archived(user_id, forced=True)])
    user_item = user_dynamo.get_user(user_id)
    assert user_item.get('postCount', 0) == 0
    assert user_item.get('postArchivedCount', 0) == 3
    assert user_item.get('postForcedArchivingCount', 0) == 2

    # verify can't go negative
    with pytest.raises(user_dynamo.client.exceptions.TransactionCanceledException):
        user_dynamo.client.transact_write_items([user_dynamo.transact_post_archived(user_id)])


def test_transact_post_restored(user_dynamo):
    # set up & verify starting state
    user_id = 'user-id'
    user_dynamo.add_user(user_id, 'username')
    user_dynamo.client.transact_write_items([user_dynamo.transact_post_completed(user_id)])
    user_dynamo.client.transact_write_items([user_dynamo.transact_post_completed(user_id)])
    user_dynamo.client.transact_write_items([user_dynamo.transact_post_archived(user_id)])
    user_dynamo.client.transact_write_items([user_dynamo.transact_post_archived(user_id)])
    user_item = user_dynamo.get_user(user_id)
    assert user_item['userId'] == user_id
    assert user_item.get('postCount', 0) == 0
    assert user_item.get('postArchivedCount', 0) == 2

    # restore
    user_dynamo.client.transact_write_items([user_dynamo.transact_post_restored(user_id)])
    user_item = user_dynamo.get_user(user_id)
    assert user_item.get('postCount', 0) == 1
    assert user_item.get('postArchivedCount', 0) == 1

    # restore another
    user_dynamo.client.transact_write_items([user_dynamo.transact_post_restored(user_id)])
    user_item = user_dynamo.get_user(user_id)
    assert user_item.get('postCount', 0) == 2
    assert user_item.get('postArchivedCount', 0) == 0

    # verify can't go negative
    with pytest.raises(user_dynamo.client.exceptions.TransactionCanceledException):
        user_dynamo.client.transact_write_items([user_dynamo.transact_post_restored(user_id)])


def test_transact_post_deleted(user_dynamo):
    # set up & verify starting state
    user_id = 'user-id'
    user_dynamo.add_user(user_id, 'username')
    user_dynamo.client.transact_write_items([user_dynamo.transact_post_completed(user_id)])
    user_dynamo.client.transact_write_items([user_dynamo.transact_post_completed(user_id)])
    user_dynamo.client.transact_write_items([user_dynamo.transact_post_archived(user_id)])
    user_item = user_dynamo.get_user(user_id)
    assert user_item['userId'] == user_id
    assert user_item.get('postCount', 0) == 1
    assert user_item.get('postArchivedCount', 0) == 1
    assert user_item.get('postDeletedCount', 0) == 0

    # delete the archived post
    user_dynamo.client.transact_write_items(
        [user_dynamo.transact_post_deleted(user_id, prev_status=PostStatus.ARCHIVED)]
    )
    user_item = user_dynamo.get_user(user_id)
    assert user_item.get('postCount', 0) == 1
    assert user_item.get('postArchivedCount', 0) == 0
    assert user_item.get('postDeletedCount', 0) == 1

    # delete the completed post
    user_dynamo.client.transact_write_items(
        [user_dynamo.transact_post_deleted(user_id, prev_status=PostStatus.COMPLETED)]
    )
    user_item = user_dynamo.get_user(user_id)
    assert user_item.get('postCount', 0) == 0
    assert user_item.get('postArchivedCount', 0) == 0
    assert user_item.get('postDeletedCount', 0) == 2

    # delete a pending post
    user_dynamo.client.transact_write_items(
        [user_dynamo.transact_post_deleted(user_id, prev_status=PostStatus.PENDING)]
    )
    user_item = user_dynamo.get_user(user_id)
    assert user_item.get('postCount', 0) == 0
    assert user_item.get('postArchivedCount', 0) == 0
    assert user_item.get('postDeletedCount', 0) == 3

    # verify can't go negative for completed posts
    with pytest.raises(user_dynamo.client.exceptions.TransactionCanceledException):
        user_dynamo.client.transact_write_items(
            [user_dynamo.transact_post_deleted(user_id, prev_status=PostStatus.COMPLETED)]
        )

    # verify can't go negative for archived posts
    with pytest.raises(user_dynamo.client.exceptions.TransactionCanceledException):
        user_dynamo.client.transact_write_items(
            [user_dynamo.transact_post_deleted(user_id, prev_status=PostStatus.ARCHIVED)]
        )


def test_transact_comment_added_and_transact_comment_deleted(user_dynamo):
    user_id = 'user-id'
    transact_added = user_dynamo.transact_comment_added(user_id)
    transact_deleted_willfull = user_dynamo.transact_comment_deleted(user_id)
    transact_deleted_forced = user_dynamo.transact_comment_deleted(user_id, forced=True)

    # set up & verify starting state
    user_dynamo.add_user(user_id, 'username')
    user_item = user_dynamo.get_user(user_id)
    assert user_item['userId'] == user_id
    assert user_item.get('commentCount', 0) == 0
    assert user_item.get('commentDeletedCount', 0) == 0
    assert user_item.get('commentForcedDeletionCount', 0) == 0

    # three comments, one by one
    user_dynamo.client.transact_write_items([transact_added])
    assert user_dynamo.get_user(user_id).get('commentCount', 0) == 1
    user_dynamo.client.transact_write_items([transact_added])
    assert user_dynamo.get_user(user_id).get('commentCount', 0) == 2
    user_dynamo.client.transact_write_items([transact_added])
    user_item = user_dynamo.get_user(user_id)
    assert user_item.get('commentCount', 0) == 3
    assert user_item.get('commentDeletedCount', 0) == 0
    assert user_item.get('commentForcedDeletionCount', 0) == 0

    # delete one comment, forced
    user_dynamo.client.transact_write_items([transact_deleted_forced])
    user_item = user_dynamo.get_user(user_id)
    assert user_item.get('commentCount', 0) == 2
    assert user_item.get('commentDeletedCount', 0) == 1
    assert user_item.get('commentForcedDeletionCount', 0) == 1

    # delete another comment, not forced
    user_dynamo.client.transact_write_items([transact_deleted_willfull])
    user_item = user_dynamo.get_user(user_id)
    assert user_item.get('commentCount', 0) == 1
    assert user_item.get('commentDeletedCount', 0) == 2
    assert user_item.get('commentForcedDeletionCount', 0) == 1

    # delete one comment, forced
    user_dynamo.client.transact_write_items([transact_deleted_forced])
    user_item = user_dynamo.get_user(user_id)
    assert user_item.get('commentCount', 0) == 0
    assert user_item.get('commentDeletedCount', 0) == 3
    assert user_item.get('commentForcedDeletionCount', 0) == 2

    # verify can't go negative
    with pytest.raises(user_dynamo.client.exceptions.TransactionCanceledException):
        user_dynamo.client.transact_write_items([transact_deleted_willfull])
    with pytest.raises(user_dynamo.client.exceptions.TransactionCanceledException):
        user_dynamo.client.transact_write_items([transact_deleted_forced])


def test_transact_card_added_and_transact_card_deleted(user_dynamo):
    user_id = 'user-id'
    transact_added = user_dynamo.transact_card_added(user_id)
    transact_deleted = user_dynamo.transact_card_deleted(user_id)

    # set up & verify starting state
    user_dynamo.add_user(user_id, 'username')
    assert user_dynamo.get_user(user_id).get('commentCount', 0) == 0

    # two cards, one by one
    user_dynamo.client.transact_write_items([transact_added])
    assert user_dynamo.get_user(user_id).get('cardCount', 0) == 1
    user_dynamo.client.transact_write_items([transact_added])
    assert user_dynamo.get_user(user_id).get('cardCount', 0) == 2

    # delete those cards, one by one
    user_dynamo.client.transact_write_items([transact_deleted])
    assert user_dynamo.get_user(user_id).get('cardCount', 0) == 1
    user_dynamo.client.transact_write_items([transact_deleted])
    assert user_dynamo.get_user(user_id).get('cardCount', 0) == 0

    # verify can't go negative
    with pytest.raises(user_dynamo.client.exceptions.TransactionCanceledException):
        user_dynamo.client.transact_write_items([transact_deleted])
