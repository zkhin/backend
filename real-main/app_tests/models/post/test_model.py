from datetime import datetime
from unittest.mock import call, Mock

from isodate.duration import Duration
import pytest

from app.models.followed_first_story import FollowedFirstStoryManager


@pytest.fixture
def user(user_manager):
    yield user_manager.create_cognito_only_user('pbuid', 'pbUname')


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user.id, 'pid1', text='t')


@pytest.fixture
def albums(album_manager, user):
    album1 = album_manager.add_album(user.id, 'aid-1', 'album name')
    album2 = album_manager.add_album(user.id, 'aid-2', 'album name')
    yield [album1, album2]


@pytest.fixture
def post_with_expiration(post_manager, user_manager):
    user = user_manager.create_cognito_only_user('pbuid2', 'pbUname2')
    yield post_manager.add_post(user.id, 'pid2', text='t', lifetime_duration=Duration(hours=1))


@pytest.fixture
def post_with_media(post_manager, user_manager):
    user = user_manager.create_cognito_only_user('pbuid2', 'pbUname2')
    yield post_manager.add_post(user.id, 'pid2', media_uploads=[{'mediaId': 'mid', 'mediaType': 'IMAGE'}], text='t')


def test_refresh_item(post):
    # go behind their back and edit the post in the DB
    new_post_item = post.dynamo.increment_viewed_by_count(post.id)
    assert new_post_item != post.item

    # now refresh the item, and check they now do match
    post.refresh_item()
    assert new_post_item == post.item


def test_set_expires_at(post):
    # add a post without an expires at
    assert 'expiresAt' not in post.item

    # set the expires at to something
    now = datetime.utcnow()
    post.followed_first_story_manager = Mock(FollowedFirstStoryManager({}))
    post.set_expires_at(now)
    assert post.item['expiresAt'] == now.isoformat() + 'Z'

    # make sure that stuck in db
    post.refresh_item()
    assert post.item['expiresAt'] == now.isoformat() + 'Z'

    # check that the followed_first_story_manager was called correctly
    assert post.followed_first_story_manager.mock_calls == [
        call.refresh_after_story_change(story_prev=None, story_now=post.item),
    ]

    # set the expires at to something else
    post.followed_first_story_manager.reset_mock()
    now = datetime.utcnow()
    post_org_item = post.item.copy()
    post.set_expires_at(now)
    assert post.item['expiresAt'] == now.isoformat() + 'Z'

    # make sure that stuck in db
    post.refresh_item()
    assert post.item['expiresAt'] == now.isoformat() + 'Z'

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
    assert list(post_manager.media_dynamo.generate_by_post(post.id)) == []

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
    assert list(post_manager.media_dynamo.generate_by_post(post.id))

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


def test_set_album_errors(album_manager, post_manager, user_manager, post):
    # album doesn't exist
    with pytest.raises(post_manager.exceptions.PostException):
        post.set_album('aid-dne')

    # album is owned by a different user
    user2 = user_manager.create_cognito_only_user('ouid', 'oUname')
    album = album_manager.add_album(user2.id, 'aid-2', 'album name')
    with pytest.raises(post_manager.exceptions.PostException):
        post.set_album(album.id)


def test_set_album(albums, post):
    album1, album2 = albums

    # verify starting state
    assert 'albumId' not in post.item
    album1.item.get('postCount', 0) == 0
    album2.item.get('postCount', 0) == 0

    # go from no album to an album
    post.set_album(album1.id)
    assert post.item['albumId'] == album1.id
    album1.refresh_item()
    album1.item.get('postCount', 0) == 1
    album2.refresh_item()
    album2.item.get('postCount', 0) == 0

    # change the album
    post.set_album(album2.id)
    assert post.item['albumId'] == album2.id
    album1.refresh_item()
    album1.item.get('postCount', 0) == 0
    album2.refresh_item()
    album2.item.get('postCount', 0) == 1

    # no-op
    post.set_album(album2.id)
    assert post.item['albumId'] == album2.id
    album1.refresh_item()
    album1.item.get('postCount', 0) == 0
    album2.refresh_item()
    album2.item.get('postCount', 0) == 1

    # remove post from all albums
    post.set_album(None)
    assert 'albumId' not in post.item
    album1.refresh_item()
    album1.item.get('postCount', 0) == 0
    album2.refresh_item()
    album2.item.get('postCount', 0) == 0
