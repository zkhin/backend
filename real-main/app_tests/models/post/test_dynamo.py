from datetime import datetime, timedelta

from isodate import duration
import pytest

from app.models.post import exceptions
from app.models.post.dynamo import PostDynamo
from app.models.post.enums import PostStatus


@pytest.fixture
def post_dynamo(dynamo_client):
    yield PostDynamo(dynamo_client)


def test_post_does_not_exist(post_dynamo):
    post_id = 'my-post-id'
    resp = post_dynamo.get_post(post_id)
    assert resp is None


def test_post_exists(post_dynamo):
    post_id = 'my-post-id'
    user_id = 'my-user-id'

    # add the post
    transact = post_dynamo.transact_add_pending_post(user_id, post_id, text='lore ipsum')
    post_dynamo.client.transact_write_items([transact])

    # post exists now
    resp = post_dynamo.get_post(post_id)
    assert resp['postId'] == post_id

    # check strongly_consistent kwarg accepted
    resp = post_dynamo.get_post(post_id, strongly_consistent=True)
    assert resp['postId'] == post_id


def test_transact_add_pending_post_sans_options(post_dynamo):
    user_id = 'pbuid'
    post_id = 'pid'
    posted_at = datetime.utcnow()

    # add the post
    transacts = [post_dynamo.transact_add_pending_post(user_id, post_id, posted_at=posted_at)]
    post_dynamo.client.transact_write_items(transacts)

    # retrieve post, check format
    posted_at_str = posted_at.isoformat() + 'Z'
    post_item = post_dynamo.get_post(post_id)
    assert post_item == {
        'schemaVersion': 1,
        'partitionKey': 'post/pid',
        'sortKey': '-',
        'gsiA2PartitionKey': 'post/pbuid',
        'gsiA2SortKey': f'{PostStatus.PENDING}/{posted_at_str}',
        'postedByUserId': 'pbuid',
        'postId': 'pid',
        'postStatus': PostStatus.PENDING,
        'postedAt': posted_at_str,
    }


def test_transact_add_pending_post_with_options(post_dynamo):
    user_id = 'pbuid'
    post_id = 'pid'
    album_id = 'aid'
    posted_at = datetime.utcnow()
    expires_at = datetime.utcnow()
    text = 'lore @ipsum'
    text_tags = [{'tag': '@ipsum', 'userId': 'uid'}]

    transacts = [post_dynamo.transact_add_pending_post(
        user_id, post_id, posted_at=posted_at, expires_at=expires_at, text=text, text_tags=text_tags,
        comments_disabled=True, likes_disabled=False, sharing_disabled=False, verification_hidden=True,
        album_id=album_id,
    )]
    post_dynamo.client.transact_write_items(transacts)

    # retrieve post, check format
    posted_at_str = posted_at.isoformat() + 'Z'
    expires_at_str = expires_at.isoformat() + 'Z'
    post_item = post_dynamo.get_post(post_id)
    assert post_item == {
        'schemaVersion': 1,
        'partitionKey': 'post/pid',
        'sortKey': '-',
        'gsiA2PartitionKey': 'post/pbuid',
        'gsiA2SortKey': PostStatus.PENDING + '/' + posted_at_str,
        'postedByUserId': 'pbuid',
        'postId': 'pid',
        'postStatus': PostStatus.PENDING,
        'albumId': 'aid',
        'postedAt': posted_at_str,
        'expiresAt': expires_at_str,
        'gsiA1PartitionKey': 'post/pbuid',
        'gsiA1SortKey': PostStatus.PENDING + '/' + expires_at_str,
        'gsiK1PartitionKey': 'post/' + expires_at_str[:10],
        'gsiK1SortKey': expires_at_str[11:-1],
        'gsiK2PartitionKey': 'post/aid',
        'gsiK2SortKey': PostStatus.PENDING + '/' + posted_at_str,
        'text': text,
        'textTags': text_tags,
        'commentsDisabled': True,
        'likesDisabled': False,
        'sharingDisabled': False,
        'verificationHidden': True,
    }


def test_transact_add_post_already_exists(post_dynamo):
    user_id = 'uid'
    post_id = 'pid'

    # add the post
    transacts = [post_dynamo.transact_add_pending_post(user_id, post_id)]
    post_dynamo.client.transact_write_items(transacts)

    # try to add it again
    with pytest.raises(post_dynamo.client.exceptions.ConditionalCheckFailedException):
        post_dynamo.client.transact_write_items(transacts)


def test_generate_posts_by_user(post_dynamo):
    user_id = 'uid'

    # add & complete a post by another user as bait (shouldn't show up in our upcoming queries)
    transacts = [post_dynamo.transact_add_pending_post('other-uid', 'pidX', text='lore ipsum')]
    post_dynamo.client.transact_write_items(transacts)
    post_item = post_dynamo.get_post('pidX')
    transacts = [post_dynamo.transact_set_post_status(post_item, PostStatus.COMPLETED)]
    post_dynamo.client.transact_write_items(transacts)

    # test generate no posts
    assert list(post_dynamo.generate_posts_by_user(user_id)) == []

    # we add a post
    post_id = 'pid'
    transacts = [post_dynamo.transact_add_pending_post(user_id, post_id, text='lore ipsum')]
    post_dynamo.client.transact_write_items(transacts)
    post_item = post_dynamo.get_post(post_id)

    # should see if if we generate all statues, but not for COMPLETED status only
    assert [p['postId'] for p in post_dynamo.generate_posts_by_user(user_id)] == [post_id]
    assert [p['postId'] for p in post_dynamo.generate_posts_by_user(user_id, completed=True)] == []
    assert [p['postId'] for p in post_dynamo.generate_posts_by_user(user_id, completed=False)] == [post_id]

    # complete the post
    transacts = [post_dynamo.transact_set_post_status(post_item, PostStatus.COMPLETED)]
    post_dynamo.client.transact_write_items(transacts)

    # should see if if we generate all statues, and for COMPLETED status only
    assert [p['postId'] for p in post_dynamo.generate_posts_by_user(user_id)] == [post_id]
    assert [p['postId'] for p in post_dynamo.generate_posts_by_user(user_id, completed=True)] == [post_id]
    assert [p['postId'] for p in post_dynamo.generate_posts_by_user(user_id, completed=False)] == []

    # we add another post
    post_id_2 = 'pid2'
    transacts = [post_dynamo.transact_add_pending_post(user_id, post_id_2, text='lore ipsum')]
    post_dynamo.client.transact_write_items(transacts)

    # check genertaion
    post_ids = [p['postId'] for p in post_dynamo.generate_posts_by_user(user_id)]
    assert sorted(post_ids) == ['pid', 'pid2']
    assert [p['postId'] for p in post_dynamo.generate_posts_by_user(user_id, completed=True)] == [post_id]
    assert [p['postId'] for p in post_dynamo.generate_posts_by_user(user_id, completed=False)] == [post_id_2]


def test_transact_set_post_status(post_dynamo):
    post_id = 'my-post-id'
    user_id = 'my-user-id'

    # add a post, verify starts pending
    transacts = [post_dynamo.transact_add_pending_post(user_id, post_id, text='lore ipsum')]
    post_dynamo.client.transact_write_items(transacts)
    org_post_item = post_dynamo.get_post(post_id)
    assert org_post_item['postStatus'] == PostStatus.PENDING

    # set post status without specifying an original post id
    new_status = 'yup'
    transacts = [post_dynamo.transact_set_post_status(org_post_item, new_status)]
    post_dynamo.client.transact_write_items(transacts)
    new_post_item = post_dynamo.get_post(post_id)
    assert new_post_item.pop('postStatus') == new_status
    assert new_post_item.pop('gsiA2SortKey').startswith(new_status + '/')
    assert {**new_post_item, **{k: org_post_item[k] for k in ('gsiA2SortKey', 'postStatus')}} == org_post_item

    # set post status *with* specifying an original post id
    new_status = 'new new'
    original_post_id = 'opid'
    transacts = [post_dynamo.transact_set_post_status(new_post_item, new_status, original_post_id=original_post_id)]
    post_dynamo.client.transact_write_items(transacts)
    new_post_item = post_dynamo.get_post(post_id)
    assert new_post_item.pop('postStatus') == new_status
    assert new_post_item.pop('gsiA2SortKey').startswith(new_status + '/')
    assert new_post_item.pop('originalPostId') == original_post_id
    assert {**new_post_item, **{k: org_post_item[k] for k in ('gsiA2SortKey', 'postStatus')}} == org_post_item


def test_transact_set_post_status_with_expires_at_and_album_id(post_dynamo):
    post_id = 'my-post-id'
    user_id = 'my-user-id'

    # add a post, verify starts pending
    expires_at = datetime.utcnow() + duration.Duration(days=1)
    post_dynamo.client.transact_write_items([
        post_dynamo.transact_add_pending_post(user_id, post_id, text='l', expires_at=expires_at, album_id='aid'),
    ])
    post_item = post_dynamo.get_post(post_id)
    assert post_item['postStatus'] == PostStatus.PENDING

    new_status = 'yup'
    transacts = [post_dynamo.transact_set_post_status(post_item, new_status)]
    post_dynamo.client.transact_write_items(transacts)
    post_item = post_dynamo.get_post(post_id)
    assert post_item['postStatus'] == new_status
    assert post_item['gsiA2SortKey'].startswith(new_status + '/')
    assert post_item['gsiA1SortKey'].startswith(new_status + '/')
    assert post_item['gsiK2SortKey'].startswith(new_status + '/')


def test_transact_increment_decrement_flag_count(post_dynamo):
    post_id = 'pid'

    # add a post
    transacts = [post_dynamo.transact_add_pending_post('uid', post_id, text='lore ipsum')]
    post_dynamo.client.transact_write_items(transacts)

    # check it has no flags
    post_item = post_dynamo.get_post(post_id)
    assert post_item.get('flagCount', 0) == 0

    # check first increment works
    transacts = [post_dynamo.transact_increment_flag_count(post_id)]
    post_dynamo.client.transact_write_items(transacts)
    post_item = post_dynamo.get_post(post_id)
    assert post_item.get('flagCount', 0) == 1

    # check decrement works
    transacts = [post_dynamo.transact_decrement_flag_count(post_id)]
    post_dynamo.client.transact_write_items(transacts)
    post_item = post_dynamo.get_post(post_id)
    assert post_item.get('flagCount', 0) == 0

    # check can't decrement below zero
    transacts = [post_dynamo.transact_decrement_flag_count(post_id)]
    with pytest.raises(post_dynamo.client.boto3_client.exceptions.ConditionalCheckFailedException):
        post_dynamo.client.transact_write_items(transacts)


def test_batch_get_posted_by_user_ids_not_found(post_dynamo):
    post_id = 'my-post-id'
    resp = post_dynamo.batch_get_posted_by_user_ids([post_id])
    assert resp == []


def test_batch_get_posted_by_user_ids(post_dynamo):
    user_id_1 = 'my-user-id-1'
    user_id_2 = 'my-user-id-2'
    post_id_1 = 'my-post-id-1'
    post_id_2 = 'my-post-id-2'
    post_id_3 = 'my-post-id-3'
    post_id_4 = 'my-post-id-4'

    # first user adds two posts, second user adds one post, leaves one post DNE
    transacts = [
        post_dynamo.transact_add_pending_post(user_id_1, post_id_1, text='lore ipsum'),
        post_dynamo.transact_add_pending_post(user_id_1, post_id_2, text='lore ipsum'),
        post_dynamo.transact_add_pending_post(user_id_2, post_id_3, text='lore ipsum'),
    ]
    post_dynamo.client.transact_write_items(transacts)

    resp = post_dynamo.batch_get_posted_by_user_ids([post_id_1, post_id_2, post_id_3, post_id_4])
    assert sorted(resp) == [user_id_1, user_id_1, user_id_2]


def test_increment_viewed_by_count_doesnt_exist(post_dynamo):
    post_id = 'doesnt-exist'
    with pytest.raises(exceptions.PostDoesNotExist):
        post_dynamo.increment_viewed_by_count(post_id)


def test_increment_viewed_by_counts(post_dynamo):
    # create a post
    post_id = 'post-id'
    transacts = [post_dynamo.transact_add_pending_post('uid', post_id, text='lore ipsum')]
    post_dynamo.client.transact_write_items(transacts)

    # verify it has no view count
    post_item = post_dynamo.get_post(post_id)
    assert post_item.get('viewedByCount', 0) == 0

    # record a view
    post_item = post_dynamo.increment_viewed_by_count(post_id)
    assert post_item['postId'] == post_id
    assert post_item['viewedByCount'] == 1

    # verify it really got the view count
    post_item = post_dynamo.get_post(post_id)
    assert post_item['postId'] == post_id
    assert post_item['viewedByCount'] == 1

    # record another view
    post_item = post_dynamo.increment_viewed_by_count(post_id)
    assert post_item['postId'] == post_id
    assert post_item['viewedByCount'] == 2

    # verify it really got the view count
    post_item = post_dynamo.get_post(post_id)
    assert post_item['postId'] == post_id
    assert post_item['viewedByCount'] == 2


def test_set_expires_at_matches_creating_story_directly(post_dynamo):
    # create a post with a lifetime, then delete it
    user_id = 'uid'
    post_id = 'post-id'
    text = 'lore ipsum'
    expires_at = datetime.utcnow() + duration.Duration(hours=1)
    transacts = [post_dynamo.transact_add_pending_post(user_id, post_id, text=text, expires_at=expires_at)]
    post_dynamo.client.transact_write_items(transacts)

    org_post_item = post_dynamo.get_post(post_id)
    assert org_post_item['postId'] == post_id
    assert org_post_item['expiresAt'] == expires_at.isoformat() + 'Z'

    # delete it from the DB
    post_dynamo.client.delete_item({'Key': {
        'partitionKey': f'post/{post_id}',
        'sortKey': '-',
    }})

    # now add it to the DB, without a lifetime
    transacts = [post_dynamo.transact_add_pending_post(user_id, post_id, text=text)]
    post_dynamo.client.transact_write_items(transacts)
    new_post_item = post_dynamo.get_post(post_id)
    assert new_post_item['postId'] == post_id
    assert 'expiresAt' not in new_post_item

    # set the expires at, now the post items should match, except for postedAt timestamp
    new_post_item = post_dynamo.set_expires_at(new_post_item, expires_at)
    new_post_item['postedAt'] = org_post_item['postedAt']
    new_post_item['gsiA2SortKey'] = org_post_item['gsiA2SortKey']
    assert new_post_item == org_post_item


def test_remove_expires_at_matches_creating_story_directly(post_dynamo):
    # create a post with without lifetime, then delete it
    user_id = 'uid'
    post_id = 'post-id'
    text = 'lore ipsum'
    transacts = [post_dynamo.transact_add_pending_post(user_id, post_id, text=text)]
    post_dynamo.client.transact_write_items(transacts)
    org_post_item = post_dynamo.get_post(post_id)
    assert org_post_item['postId'] == post_id
    assert 'expiresAt' not in org_post_item

    # delete it from the DB
    post_dynamo.client.delete_item({'Key': {
        'partitionKey': f'post/{post_id}',
        'sortKey': '-',
    }})

    # now add it to the DB, with a lifetime
    expires_at = datetime.utcnow() + duration.Duration(hours=1)
    transacts = [post_dynamo.transact_add_pending_post(user_id, post_id, text=text, expires_at=expires_at)]
    post_dynamo.client.transact_write_items(transacts)
    new_post_item = post_dynamo.get_post(post_id)
    assert new_post_item['postId'] == post_id
    assert new_post_item['expiresAt'] == expires_at.isoformat() + 'Z'

    # remove the expires at, now the post items should match
    new_post_item = post_dynamo.remove_expires_at(post_id)
    new_post_item['postedAt'] = org_post_item['postedAt']
    new_post_item['gsiA2SortKey'] = org_post_item['gsiA2SortKey']
    assert new_post_item == org_post_item


def test_get_next_completed_post_to_expire_no_posts(post_dynamo):
    user_id = 'user-id'
    post = post_dynamo.get_next_completed_post_to_expire(user_id)
    assert post is None


def test_get_next_completed_post_to_expire_one_post(dynamo_client, post_dynamo):
    user_id = 'user-id'
    post_id_1 = 'post-id-1'
    expires_at = datetime.utcnow() + duration.Duration(hours=1)

    transacts = [post_dynamo.transact_add_pending_post(user_id, post_id_1, text='t', expires_at=expires_at)]
    post_dynamo.client.transact_write_items(transacts)
    post_item = post_dynamo.get_post(post_id_1)
    post_dynamo.client.transact_write_items([post_dynamo.transact_set_post_status(post_item, PostStatus.COMPLETED)])

    assert post_dynamo.get_next_completed_post_to_expire(user_id)['postId'] == post_id_1


def test_get_next_completed_post_to_expire_two_posts(dynamo_client, post_dynamo):
    user_id = 'user-id'
    post_id_1, post_id_2 = 'post-id-1', 'post-id-2'
    now = datetime.utcnow()
    expires_at_1, expires_at_2 = now + duration.Duration(days=1), now + duration.Duration(hours=12)

    # add those posts
    transacts = [
        post_dynamo.transact_add_pending_post(user_id, post_id_1, text='t', expires_at=expires_at_1),
        post_dynamo.transact_add_pending_post(user_id, post_id_2, text='t', expires_at=expires_at_2),
    ]
    post_dynamo.client.transact_write_items(transacts)
    post1 = post_dynamo.get_post(post_id_1)
    post2 = post_dynamo.get_post(post_id_2)

    # check niether of them show up
    assert post_dynamo.get_next_completed_post_to_expire(user_id) is None

    # complete one of them, check
    post_dynamo.client.transact_write_items([post_dynamo.transact_set_post_status(post1, PostStatus.COMPLETED)])
    post1 = post_dynamo.get_post(post_id_1)
    assert post_dynamo.get_next_completed_post_to_expire(user_id) == post1
    assert post_dynamo.get_next_completed_post_to_expire(user_id, exclude_post_id=post_id_1) is None

    # complete the other, check
    post_dynamo.client.transact_write_items([post_dynamo.transact_set_post_status(post2, PostStatus.COMPLETED)])
    post2 = post_dynamo.get_post(post_id_2)
    assert post_dynamo.get_next_completed_post_to_expire(user_id) == post2
    assert post_dynamo.get_next_completed_post_to_expire(user_id, exclude_post_id=post_id_1) == post2
    assert post_dynamo.get_next_completed_post_to_expire(user_id, exclude_post_id=post_id_2) == post1


def test_set_no_values(post_dynamo):
    with pytest.raises(Exception, match='edit'):
        post_dynamo.set('post-id')


def test_set_text(post_dynamo, dynamo_client):
    # create a post with some text
    text = 'for shiz'
    transacts = [post_dynamo.transact_add_pending_post('uidA', 'pid1', text=text, text_tags=[])]
    post_dynamo.client.transact_write_items(transacts)
    post_item = post_dynamo.get_post('pid1')
    assert post_item['text'] == text
    assert post_item['textTags'] == []

    # edit that text
    new_text = 'over the rainbow'
    post_item = post_dynamo.set('pid1', text=new_text, text_tags=[])
    assert post_item['text'] == new_text
    assert post_item['textTags'] == []
    post_item = post_dynamo.get_post('pid1')
    assert post_item['text'] == new_text
    assert post_item['textTags'] == []

    # edit that text with a tag
    new_text = 'over the @rainbow'
    new_text_tags = [{'tag': '@rainbow', 'userId': 'tagged-uid'}]
    post_item = post_dynamo.set('pid1', text=new_text, text_tags=new_text_tags)
    assert post_item['text'] == new_text
    assert post_item['textTags'] == new_text_tags
    post_item = post_dynamo.get_post('pid1')
    assert post_item['text'] == new_text
    assert post_item['textTags'] == new_text_tags

    # delete that text
    post_item = post_dynamo.set('pid1', text='')
    assert 'text' not in post_item
    assert 'textTags' not in post_item
    post_item = post_dynamo.get_post('pid1')
    assert 'text' not in post_item
    assert 'textTags' not in post_item


def test_set_comments_disabled(post_dynamo, dynamo_client):
    # create a post with some text, media objects
    transacts = [post_dynamo.transact_add_pending_post('uidA', 'pid1', text='t')]
    post_dynamo.client.transact_write_items(transacts)
    post_item = post_dynamo.get_post('pid1')
    assert 'commentsDisabled' not in post_item

    # edit it back and forth
    post_item = post_dynamo.set('pid1', comments_disabled=True)
    assert post_item['commentsDisabled'] is True
    post_item = post_dynamo.set('pid1', comments_disabled=False)
    assert post_item['commentsDisabled'] is False

    # double check the value stuck
    post_item = post_dynamo.get_post('pid1')
    assert post_item['commentsDisabled'] is False


def test_set_likes_disabled(post_dynamo, dynamo_client):
    # create a post with some text, media objects
    transacts = [post_dynamo.transact_add_pending_post('uidA', 'pid1', text='t')]
    post_dynamo.client.transact_write_items(transacts)
    post_item = post_dynamo.get_post('pid1')
    assert 'likesDisabled' not in post_item

    # edit it back and forth
    post_item = post_dynamo.set('pid1', likes_disabled=True)
    assert post_item['likesDisabled'] is True
    post_item = post_dynamo.set('pid1', likes_disabled=False)
    assert post_item['likesDisabled'] is False

    # double check the value stuck
    post_item = post_dynamo.get_post('pid1')
    assert post_item['likesDisabled'] is False


def test_set_sharing_disabled(post_dynamo, dynamo_client):
    # create a post with some text, media objects
    transacts = [post_dynamo.transact_add_pending_post('uidA', 'pid1', text='t')]
    post_dynamo.client.transact_write_items(transacts)
    post_item = post_dynamo.get_post('pid1')
    assert 'sharingDisabled' not in post_item

    # edit it back and forth
    post_item = post_dynamo.set('pid1', sharing_disabled=True)
    assert post_item['sharingDisabled'] is True
    post_item = post_dynamo.set('pid1', sharing_disabled=False)
    assert post_item['sharingDisabled'] is False

    # double check the value stuck
    post_item = post_dynamo.get_post('pid1')
    assert post_item['sharingDisabled'] is False


def test_set_verification_hidden(post_dynamo, dynamo_client):
    # create a post with some text, media objects
    transacts = [post_dynamo.transact_add_pending_post('uidA', 'pid1', text='t')]
    post_dynamo.client.transact_write_items(transacts)
    post_item = post_dynamo.get_post('pid1')
    assert 'verificationHidden' not in post_item

    # edit it back and forth
    post_item = post_dynamo.set('pid1', verification_hidden=True)
    assert post_item['verificationHidden'] is True
    post_item = post_dynamo.set('pid1', verification_hidden=False)
    assert post_item['verificationHidden'] is False

    # double check the value stuck
    post_item = post_dynamo.get_post('pid1')
    assert post_item['verificationHidden'] is False


def test_generate_expired_post_pks_by_day(post_dynamo, dynamo_client):
    # add three posts, two that expire on the same day, and one that never expires, and complete them all
    now = datetime.utcnow()
    approx_hours_till_noon_tomorrow = 36 - now.time().hour
    lifetime_1 = duration.Duration(hours=approx_hours_till_noon_tomorrow)
    lifetime_2 = duration.Duration(hours=(approx_hours_till_noon_tomorrow + 6))
    expires_at_1 = now + lifetime_1
    expires_at_2 = now + lifetime_2

    transacts = [
        post_dynamo.transact_add_pending_post('uidA', 'post-id-1', text='no', expires_at=expires_at_1),
        post_dynamo.transact_add_pending_post('uidA', 'post-id-2', text='me', expires_at=expires_at_2),
        post_dynamo.transact_add_pending_post('uidA', 'post-id-3', text='digas'),
    ]
    post_dynamo.client.transact_write_items(transacts)
    post1 = post_dynamo.get_post('post-id-1')
    post2 = post_dynamo.get_post('post-id-2')
    post3 = post_dynamo.get_post('post-id-3')

    post_dynamo.client.transact_write_items([post_dynamo.transact_set_post_status(post1, PostStatus.COMPLETED)])
    post_dynamo.client.transact_write_items([post_dynamo.transact_set_post_status(post2, PostStatus.COMPLETED)])
    post_dynamo.client.transact_write_items([post_dynamo.transact_set_post_status(post3, PostStatus.COMPLETED)])

    expires_at_1 = datetime.fromisoformat(post1['expiresAt'][:-1])
    expires_at_date = expires_at_1.date()
    cut_off_time = expires_at_1.time()

    # before any of the posts expire - checks exclusive cut off
    expired_posts = list(post_dynamo.generate_expired_post_pks_by_day(expires_at_date, cut_off_time))
    assert expired_posts == []

    # one of the posts has expired
    cut_off_time = (expires_at_1 + duration.Duration(hours=1)).time()
    expired_posts = list(post_dynamo.generate_expired_post_pks_by_day(expires_at_date, cut_off_time))
    assert len(expired_posts) == 1
    assert expired_posts[0]['partitionKey'] == post1['partitionKey']
    assert expired_posts[0]['sortKey'] == post1['sortKey']

    # both of posts have expired
    cut_off_time = (expires_at_1 + duration.Duration(hours=7)).time()
    expired_posts = list(post_dynamo.generate_expired_post_pks_by_day(expires_at_date, cut_off_time))
    assert len(expired_posts) == 2
    assert expired_posts[0]['partitionKey'] == post1['partitionKey']
    assert expired_posts[0]['sortKey'] == post1['sortKey']
    assert expired_posts[1]['partitionKey'] == post2['partitionKey']
    assert expired_posts[1]['sortKey'] == post2['sortKey']

    # check the whole day
    expired_posts = list(post_dynamo.generate_expired_post_pks_by_day(expires_at_date))
    assert len(expired_posts) == 2
    assert expired_posts[0]['partitionKey'] == post1['partitionKey']
    assert expired_posts[0]['sortKey'] == post1['sortKey']
    assert expired_posts[1]['partitionKey'] == post2['partitionKey']
    assert expired_posts[1]['sortKey'] == post2['sortKey']


def test_generate_expired_post_pks_with_scan(post_dynamo, dynamo_client):
    # add four posts, one that expires a week ago, one that expires yesterday
    # and one that expires today, and one that doesnt expire
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    yesterday = now - timedelta(days=1)
    lifetime = duration.Duration(seconds=1)

    gen_transact = post_dynamo.transact_add_pending_post
    transacts = [
        gen_transact('u', 'p1', text='no', posted_at=week_ago, expires_at=(week_ago + lifetime)),
        gen_transact('u', 'p2', text='me', posted_at=yesterday, expires_at=(yesterday + lifetime)),
        gen_transact('u', 'p3', text='digas', posted_at=now, expires_at=(now + lifetime)),
        gen_transact('u', 'p4', text='por favor'),
    ]
    post_dynamo.client.transact_write_items(transacts)
    post1 = post_dynamo.get_post('p1')
    post2 = post_dynamo.get_post('p2')

    # scan with cutoff of yesterday should only see the post from a week ago
    expired_posts = list(post_dynamo.generate_expired_post_pks_with_scan(yesterday.date()))
    assert len(expired_posts) == 1
    assert expired_posts[0]['partitionKey'] == post1['partitionKey']
    assert expired_posts[0]['sortKey'] == post1['sortKey']

    # scan with cutoff of today should see posts of yesterday and a week ago
    expired_posts = list(post_dynamo.generate_expired_post_pks_with_scan(now.date()))
    assert len(expired_posts) == 2
    assert expired_posts[0]['partitionKey'] == post1['partitionKey']
    assert expired_posts[0]['sortKey'] == post1['sortKey']
    assert expired_posts[1]['partitionKey'] == post2['partitionKey']
    assert expired_posts[1]['sortKey'] == post2['sortKey']


def test_transact_increment_decrement_comment_count(post_dynamo):
    post_id = 'pid'

    # add a post, verify starts with no comment count
    transact = post_dynamo.transact_add_pending_post('uid', post_id, text='lore ipsum')
    post_dynamo.client.transact_write_items([transact])
    post_item = post_dynamo.get_post(post_id)
    assert post_item.get('commentCount', 0) == 0

    # verify we can't decrement count below zero
    transact = post_dynamo.transact_decrement_comment_count(post_id)
    with pytest.raises(post_dynamo.client.boto3_client.exceptions.ConditionalCheckFailedException):
        post_dynamo.client.transact_write_items([transact])
    post_item = post_dynamo.get_post(post_id)
    assert post_item.get('commentCount', 0) == 0

    # increment the count, verify
    transact = post_dynamo.transact_increment_comment_count(post_id)
    post_dynamo.client.transact_write_items([transact])
    post_item = post_dynamo.get_post(post_id)
    assert post_item.get('commentCount', 0) == 1

    # increment the count, verify
    transact = post_dynamo.transact_increment_comment_count(post_id)
    post_dynamo.client.transact_write_items([transact])
    post_item = post_dynamo.get_post(post_id)
    assert post_item.get('commentCount', 0) == 2

    # decrement the count, verify
    transact = post_dynamo.transact_decrement_comment_count(post_id)
    post_dynamo.client.transact_write_items([transact])
    post_item = post_dynamo.get_post(post_id)
    assert post_item.get('commentCount', 0) == 1


def test_transact_set_album_id(post_dynamo):
    post_id = 'pid'

    # add a post without an album_id
    transact = post_dynamo.transact_add_pending_post('uid', post_id, text='lore ipsum')
    post_dynamo.client.transact_write_items([transact])
    post_item = post_dynamo.get_post(post_id)
    assert 'albumId' not in post_item
    assert 'gsiK2PartitionKey' not in post_item
    assert 'gsiK2SortKey' not in post_item

    # set the album_id, verify that worked
    transact = post_dynamo.transact_set_album_id(post_item, 'aid')
    post_dynamo.client.transact_write_items([transact])
    post_item = post_dynamo.get_post(post_id)
    assert post_item['albumId'] == 'aid'
    assert post_item['gsiK2PartitionKey'] == 'post/aid'
    assert post_item['gsiK2SortKey'] == 'PENDING/' + post_item['postedAt']

    # change the album id, verify that worked
    transact = post_dynamo.transact_set_album_id(post_item, 'aid2')
    post_dynamo.client.transact_write_items([transact])
    post_item = post_dynamo.get_post(post_id)
    assert post_item['albumId'] == 'aid2'
    assert post_item['gsiK2PartitionKey'] == 'post/aid2'
    assert post_item['gsiK2SortKey'] == 'PENDING/' + post_item['postedAt']

    # remove the album id, verify that worked
    transact = post_dynamo.transact_set_album_id(post_item, None)
    post_dynamo.client.transact_write_items([transact])
    post_item = post_dynamo.get_post(post_id)
    assert 'albumId' not in post_item
    assert 'gsiK2PartitionKey' not in post_item
    assert 'gsiK2SortKey' not in post_item


def test_transact_set_album_id_fails_wrong_status(post_dynamo):
    post_id = 'pid'

    # add a post without an album_id
    transact = post_dynamo.transact_add_pending_post('uid', post_id, text='lore ipsum')
    post_dynamo.client.transact_write_items([transact])
    post_item = post_dynamo.get_post(post_id)
    assert 'albumId' not in post_item
    assert 'gsiK2PartitionKey' not in post_item
    assert 'gsiK2SortKey' not in post_item

    # change the in-mem status so it doesn't match dynamo
    # verify transaction fails rather than write conflicting data to db
    post_item['postStatus'] = 'COMPLETED'
    transact = post_dynamo.transact_set_album_id(post_item, 'aid2')
    with pytest.raises(post_dynamo.client.boto3_client.exceptions.ConditionalCheckFailedException):
        post_dynamo.client.transact_write_items([transact])

    # verify nothing changed
    post_item = post_dynamo.get_post(post_id)
    assert 'albumId' not in post_item
    assert 'gsiK2PartitionKey' not in post_item
    assert 'gsiK2SortKey' not in post_item


def test_generate_post_ids_in_album(post_dynamo):
    # generate for an empty set
    assert list(post_dynamo.generate_post_ids_in_album('aid-nope')) == []

    # add two posts in an album
    album_id = 'aid'
    post_id_1, post_id_2 = 'pid1', 'pid2'
    transacts = [
        post_dynamo.transact_add_pending_post('uid', post_id_1, text='lore', album_id=album_id),
        post_dynamo.transact_add_pending_post('uid', post_id_2, text='lore', album_id=album_id),
    ]
    post_dynamo.client.transact_write_items(transacts)

    # verify we can generate the post_ids of those posts
    post_ids = list(post_dynamo.generate_post_ids_in_album(album_id))
    assert len(post_ids) == 2
    assert post_id_1 in post_ids
    assert post_id_2 in post_ids
