from decimal import Decimal
from io import BytesIO
from unittest.mock import call, Mock

import pendulum
import pytest

from app.models.post.enums import PostType
from app.models.followed_first_story import FollowedFirstStoryManager


@pytest.fixture
def user(user_manager):
    yield user_manager.create_cognito_only_user('pbuid', 'pbUname')


@pytest.fixture
def user2(user_manager):
    yield user_manager.create_cognito_only_user('pbuid2', 'pbUname2')


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user.id, 'pid1', PostType.TEXT_ONLY, text='t')


@pytest.fixture
def albums(album_manager, user2):
    album1 = album_manager.add_album(user2.id, 'aid-1', 'album name')
    album2 = album_manager.add_album(user2.id, 'aid-2', 'album name')
    yield [album1, album2]


@pytest.fixture
def post_with_expiration(post_manager, user2):
    yield post_manager.add_post(
        user2.id, 'pid2', PostType.TEXT_ONLY, text='t', lifetime_duration=pendulum.duration(hours=1),
    )


@pytest.fixture
def post_with_media(post_manager, user2, image_data_b64, mock_post_verification_api):
    yield post_manager.add_post(
        user2.id, 'pid2', PostType.IMAGE, media_uploads=[{'mediaId': 'mid', 'imageData': image_data_b64}], text='t',
    )


def test_refresh_item(post):
    # go behind their back and edit the post in the DB
    new_post_item = post.dynamo.increment_viewed_by_count(post.id)
    assert new_post_item != post.item

    # now refresh the item, and check they now do match
    post.refresh_item()
    assert new_post_item == post.item


def test_get_native_image_buffer(post, post_with_media):
    # verify works for text post
    buf = post.get_native_image_buffer()
    assert isinstance(buf, BytesIO)
    assert buf.read()

    # verify works for completed image post
    buf = post_with_media.get_native_image_buffer()
    assert isinstance(buf, BytesIO)
    assert buf.read()

    # verify raises exception for non-completed image post
    post_with_media.item['postStatus'] = post.enums.PostStatus.PENDING  # in mem is sufficient
    with pytest.raises(post.exceptions.PostException, match='PENDING'):
        post_with_media.get_native_image_buffer()


def test_get_1080p_image_buffer(post, post_with_media):
    # verify works for text post
    buf = post.get_1080p_image_buffer()
    assert isinstance(buf, BytesIO)
    assert buf.read()

    # verify works for completed image post
    buf = post_with_media.get_1080p_image_buffer()
    assert isinstance(buf, BytesIO)
    assert buf.read()

    # verify raises exception for non-completed image post
    post_with_media.item['postStatus'] = post.enums.PostStatus.PENDING  # in mem is sufficient
    with pytest.raises(post.exceptions.PostException, match='PENDING'):
        post_with_media.get_1080p_image_buffer()


def test_set_expires_at(post):
    # add a post without an expires at
    assert 'expiresAt' not in post.item

    # set the expires at to something
    now = pendulum.now('utc')
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.set_expires_at(now)
    assert post.item['expiresAt'] == now.to_iso8601_string()

    # make sure that stuck in db
    post.refresh_item()
    assert post.item['expiresAt'] == now.to_iso8601_string()

    # check that the followed_first_story_manager was called correctly
    assert post.followed_first_story_manager.mock_calls == [
        call.refresh_after_story_change(story_prev=None, story_now=post.item),
    ]

    # set the expires at to something else
    post.followed_first_story_manager.reset_mock()
    now = pendulum.now('utc')
    post_org_item = post.item.copy()
    post.set_expires_at(now)
    assert post.item['expiresAt'] == now.to_iso8601_string()

    # make sure that stuck in db
    post.refresh_item()
    assert post.item['expiresAt'] == now.to_iso8601_string()

    # check that the followed_first_story_manager was called correctly
    assert post.followed_first_story_manager.mock_calls == [
        call.refresh_after_story_change(story_prev=post_org_item, story_now=post.item),
    ]


def test_clear_expires_at(post_with_expiration):
    # add a post with an expires at
    post = post_with_expiration
    assert 'expiresAt' in post.item

    # remove the expires at
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post_org_item = post.item.copy()
    post.set_expires_at(None)
    assert 'expiresAt' not in post.item

    # make sure that stuck in db
    post.refresh_item()
    assert 'expiresAt' not in post.item

    # check that the followed_first_story_manager was called correctly
    assert post.followed_first_story_manager.mock_calls == [
        call.refresh_after_story_change(story_prev=post_org_item, story_now=None),
    ]


def test_set(post, user):
    username = user.item['username']
    org_text = post.item['text']

    # verify starting values
    assert post.item['text'] == org_text
    assert post.item['textTags'] == []
    assert post.item.get('commentsDisabled', False) is False
    assert post.item.get('likesDisabled', False) is False
    assert post.item.get('sharingDisabled', False) is False
    assert post.item.get('verificationHidden', False) is False

    # do some edits
    new_text = f'its a new dawn, right @{user.item["username"]}, its a new day'
    post.set(text=new_text, comments_disabled=True, likes_disabled=True, sharing_disabled=True,
             verification_hidden=True)

    # verify new values
    assert post.item['text'] == new_text
    assert post.item['textTags'] == [{'tag': f'@{username}', 'userId': user.id}]
    assert post.item.get('commentsDisabled', False) is True
    assert post.item.get('likesDisabled', False) is True
    assert post.item.get('sharingDisabled', False) is True
    assert post.item.get('verificationHidden', False) is True

    # edit some params, ignore others
    post.set(likes_disabled=False, verification_hidden=False)

    # verify only edited values changed
    assert post.item['text'] == new_text
    assert post.item['textTags'] == [{'tag': f'@{username}', 'userId': user.id}]
    assert post.item.get('commentsDisabled', False) is True
    assert post.item.get('likesDisabled', False) is False
    assert post.item.get('sharingDisabled', False) is True
    assert post.item.get('verificationHidden', False) is False


def test_set_cant_create_contentless_post(post_manager, post):
    org_text = post.item['text']

    # verify the post is text-only
    assert org_text
    assert list(post_manager.media_manager.dynamo.generate_by_post(post.id)) == []

    # verify we can't set the text to null on that post
    with pytest.raises(post_manager.exceptions.PostException):
        post.set(text='')

    # check no changes anywhere
    assert post.item['text'] == org_text
    post.refresh_item()
    assert post.item['text'] == org_text


def test_set_text_to_null_media_post(post_manager, post_with_media):
    post = post_with_media
    org_text = post.item['text']

    # verify the post has media and text
    assert org_text
    assert list(post_manager.media_manager.dynamo.generate_by_post(post.id))

    # verify we can null out the text on that post if we want
    post.set(text='')
    assert 'text' not in post.item
    assert 'textTags' not in post.item
    post.refresh_item()
    assert 'text' not in post.item
    assert 'textTags' not in post.item


def test_serailize(user, post, user_manager):
    resp = post.serialize('caller-uid')
    assert resp.pop('postedBy')['userId'] == user.id
    assert resp == post.item


def test_set_album_errors(album_manager, post_manager, user_manager, post, post_with_media, user):
    # album doesn't exist
    with pytest.raises(post_manager.exceptions.PostException) as err:
        post_with_media.set_album('aid-dne')
    assert 'does not exist' in str(err)

    # album is owned by a different user
    user2 = user_manager.create_cognito_only_user('ouid', 'oUname')
    album = album_manager.add_album(user2.id, 'aid-2', 'album name')
    with pytest.raises(post_manager.exceptions.PostException) as err:
        post_with_media.set_album(album.id)
    assert 'belong to different users' in str(err)


def test_set_album_completed_post(albums, post_with_media):
    post = post_with_media
    album1, album2 = albums

    # verify starting state
    assert 'albumId' not in post.item
    assert album1.item.get('postCount', 0) == 0
    assert album2.item.get('postCount', 0) == 0
    assert album1.item.get('rankCount', 0) == 0
    assert album2.item.get('rankCount', 0) == 0
    assert 'artHash' not in album1.item
    assert 'artHash' not in album2.item

    # go from no album to an album
    post.set_album(album1.id)
    assert post.item['albumId'] == album1.id
    assert post.item['gsiK3SortKey'] == 0   # album rank
    album1.refresh_item()
    assert album1.item.get('postCount', 0) == 1
    assert album1.item.get('rankCount', 0) == 1
    assert album1.item['artHash']
    album2.refresh_item()
    assert album2.item.get('postCount', 0) == 0
    assert album2.item.get('rankCount', 0) == 0
    assert 'artHash' not in album2.item

    # change the album
    post.set_album(album2.id)
    assert post.item['albumId'] == album2.id
    assert post.item['gsiK3SortKey'] == 0   # album rank
    album1.refresh_item()
    assert album1.item.get('postCount', 0) == 0
    assert album1.item.get('rankCount', 0) == 1
    assert 'artHash' not in album1.item
    album2.refresh_item()
    assert album2.item.get('postCount', 0) == 1
    assert album2.item.get('rankCount', 0) == 1
    assert album2.item['artHash']

    # no-op
    post.set_album(album2.id)
    assert post.item['albumId'] == album2.id
    assert post.item['gsiK3SortKey'] == 0   # album rank
    album1.refresh_item()
    assert album1.item.get('postCount', 0) == 0
    assert album1.item.get('rankCount', 0) == 1
    assert 'artHash' not in album1.item
    album2.refresh_item()
    assert album2.item.get('postCount', 0) == 1
    assert album2.item.get('rankCount', 0) == 1
    assert album2.item['artHash']

    # remove post from all albums
    post.set_album(None)
    assert 'albumId' not in post.item
    assert 'gsiK3SortKey' not in post.item
    album1.refresh_item()
    assert album1.item.get('postCount', 0) == 0
    assert album1.item.get('rankCount', 0) == 1
    assert 'artHash' not in album1.item
    album2.refresh_item()
    assert album2.item.get('postCount', 0) == 0
    assert album2.item.get('rankCount', 0) == 1
    assert 'artHash' not in album2.item

    # archive the post
    post.archive()

    # add it back to an album, should not increment counts
    post.set_album(album1.id)
    assert post.item['albumId'] == album1.id
    assert post.item['gsiK3SortKey'] == -1   # album rank
    album1.refresh_item()
    assert album1.item.get('postCount', 0) == 0
    assert album1.item.get('rankCount', 0) == 1
    assert 'artHash' not in album1.item


def test_set_album_text_post(post_manager, albums, user2):
    album1, album2 = albums
    post = post_manager.add_post(user2.id, 'pid', PostType.TEXT_ONLY, text='lore ipsum')

    # verify starting state
    assert 'albumId' not in post.item
    assert 'artHash' not in album1.item
    assert 'artHash' not in album2.item

    # go from no album to an album
    post.set_album(album1.id)
    assert post.item['albumId'] == album1.id
    assert post.item['gsiK3SortKey'] == 0   # album rank
    album1.refresh_item()
    assert album1.item['artHash']
    album2.refresh_item()
    assert 'artHash' not in album2.item

    # change the album
    post.set_album(album2.id)
    assert post.item['albumId'] == album2.id
    assert post.item['gsiK3SortKey'] == 0   # album rank
    album1.refresh_item()
    assert 'artHash' not in album1.item
    album2.refresh_item()
    assert album2.item['artHash']

    # remove post from all albums
    post.set_album(None)
    assert 'albumId' not in post.item
    assert 'gsiK3SortKey' not in post.item
    album1.refresh_item()
    assert 'artHash' not in album1.item
    album2.refresh_item()
    assert 'artHash' not in album2.item


def test_set_album_order_failures(user, user2, albums, post_manager, image_data_b64, mock_post_verification_api):
    post1 = post_manager.add_post(
        user.id, 'pid1', PostType.IMAGE, media_uploads=[{'mediaId': 'mid1', 'imageData': image_data_b64}],
    )
    post2 = post_manager.add_post(
        user2.id, 'pid2', PostType.IMAGE, media_uploads=[{'mediaId': 'mid2', 'imageData': image_data_b64}],
    )
    post3 = post_manager.add_post(
        user2.id, 'pid3', PostType.IMAGE, media_uploads=[{'mediaId': 'mid3', 'imageData': image_data_b64}],
    )
    post4 = post_manager.add_post(
        user2.id, 'pid4', PostType.IMAGE, media_uploads=[{'mediaId': 'mid4', 'imageData': image_data_b64}],
    )
    album1, album2 = albums

    # put post2 & post3 in first album
    post2.set_album(album1.id)
    assert post2.item['albumId'] == album1.id
    assert post2.item['gsiK3SortKey'] == 0

    post3.set_album(album1.id)
    assert post3.item['albumId'] == album1.id
    assert post3.item['gsiK3SortKey'] == pytest.approx(Decimal(1 / 3))

    # put post4 in second album
    post4.set_album(album2.id)
    assert post4.item['albumId'] == album2.id
    assert post4.item['gsiK3SortKey'] == 0

    # verify can't change order with post that DNE
    with pytest.raises(post_manager.exceptions.PostException):
        post2.set_album_order('pid-dne')

    # verify can't change order using post from diff users
    with pytest.raises(post_manager.exceptions.PostException):
        post1.set_album_order(post2.id)
    with pytest.raises(post_manager.exceptions.PostException):
        post2.set_album_order(post1.id)

    # verify can't change order with posts in diff albums
    with pytest.raises(post_manager.exceptions.PostException):
        post4.set_album_order(post2.id)
    with pytest.raises(post_manager.exceptions.PostException):
        post2.set_album_order(post4.id)

    # verify *can* change order if everything correct
    post2.set_album_order(post3.id)
    assert post2.item['albumId'] == album1.id
    assert post2.item['gsiK3SortKey'] == Decimal(0.5)


def test_set_album_order_lots_of_set_middle(user2, albums, post_manager, image_data_b64, mock_post_verification_api):
    # album with three posts in it
    album, _ = albums
    post1 = post_manager.add_post(
        user2.id, 'pid1', PostType.IMAGE, media_uploads=[{'mediaId': 'mid1', 'imageData': image_data_b64}],
        album_id=album.id,
    )
    post2 = post_manager.add_post(
        user2.id, 'pid2', PostType.IMAGE, media_uploads=[{'mediaId': 'mid2', 'imageData': image_data_b64}],
        album_id=album.id,
    )
    post3 = post_manager.add_post(
        user2.id, 'pid3', PostType.IMAGE, media_uploads=[{'mediaId': 'mid3', 'imageData': image_data_b64}],
        album_id=album.id,
    )

    # check starting state
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post1.id, post2.id, post3.id]
    assert post1.item['gsiK3SortKey'] == 0
    assert post2.item['gsiK3SortKey'] == pytest.approx(Decimal(1 / 3))
    assert post3.item['gsiK3SortKey'] == pytest.approx(Decimal(1 / 2))

    # change middle post, check order
    post3.set_album_order(post1.id)
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post1.id, post3.id, post2.id]
    assert post3.item['gsiK3SortKey'] == pytest.approx(Decimal(1 / 6))

    # change middle post, check order
    post2.set_album_order(post1.id)
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post1.id, post2.id, post3.id]
    assert post2.item['gsiK3SortKey'] == pytest.approx(Decimal(1 / 12))

    # change middle post, check order
    post3.set_album_order(post1.id)
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post1.id, post3.id, post2.id]
    assert post3.item['gsiK3SortKey'] == pytest.approx(Decimal(1 / 24))

    # change middle post, check order
    post2.set_album_order(post1.id)
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post1.id, post2.id, post3.id]
    assert post2.item['gsiK3SortKey'] == pytest.approx(Decimal(1 / 48))


def test_set_album_order_lots_of_set_front(user2, albums, post_manager, image_data_b64, mock_post_verification_api):
    # album with two posts in it
    album, _ = albums
    post1 = post_manager.add_post(
        user2.id, 'pid1', PostType.IMAGE, media_uploads=[{'mediaId': 'mid1', 'imageData': image_data_b64}],
        album_id=album.id,
    )
    post2 = post_manager.add_post(
        user2.id, 'pid2', PostType.IMAGE, media_uploads=[{'mediaId': 'mid2', 'imageData': image_data_b64}],
        album_id=album.id,
    )

    # check starting state
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post1.id, post2.id]
    assert post1.item['gsiK3SortKey'] == 0
    assert post2.item['gsiK3SortKey'] == pytest.approx(Decimal(1 / 3))

    # change first post, check order
    post2.set_album_order(None)
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post2.id, post1.id]
    assert post2.item['gsiK3SortKey'] == pytest.approx(Decimal(-2 / 4))

    # change first post, check order
    post1.set_album_order(None)
    with pytest.raises(AssertionError):  # https://github.com/spulec/moto/issues/2760
        assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post1.id, post2.id]
    assert post1.item['gsiK3SortKey'] == pytest.approx(Decimal(-3 / 5))

    # change first post, check order
    post2.set_album_order(None)
    with pytest.raises(AssertionError):  # https://github.com/spulec/moto/issues/2760
        assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post2.id, post1.id]
    assert post2.item['gsiK3SortKey'] == pytest.approx(Decimal(-4 / 6))


def test_set_album_order_lots_of_set_back(user2, albums, post_manager, image_data_b64, mock_post_verification_api):
    # album with two posts in it
    album, _ = albums
    post1 = post_manager.add_post(
        user2.id, 'pid1', PostType.IMAGE, media_uploads=[{'mediaId': 'mid1', 'imageData': image_data_b64}],
        album_id=album.id,
    )
    post2 = post_manager.add_post(
        user2.id, 'pid2', PostType.IMAGE, media_uploads=[{'mediaId': 'mid2', 'imageData': image_data_b64}],
        album_id=album.id,
    )

    # check starting state
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post1.id, post2.id]
    assert post1.item['gsiK3SortKey'] == 0
    assert post2.item['gsiK3SortKey'] == pytest.approx(Decimal(1 / 3))

    # change last post, check order
    post1.set_album_order(post2.id)
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post2.id, post1.id]
    assert post1.item['gsiK3SortKey'] == pytest.approx(Decimal(2 / 4))

    # change last post, check order
    post2.set_album_order(post1.id)
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post1.id, post2.id]
    assert post2.item['gsiK3SortKey'] == pytest.approx(Decimal(3 / 5))

    # change last post, check order
    post1.set_album_order(post2.id)
    assert list(post_manager.dynamo.generate_post_ids_in_album(album.id)) == [post2.id, post1.id]
    assert post1.item['gsiK3SortKey'] == pytest.approx(Decimal(4 / 6))
