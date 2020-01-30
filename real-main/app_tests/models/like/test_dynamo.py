from datetime import datetime

import pytest

from app.models.like.dynamo import LikeDynamo
from app.models.like.enums import LikeStatus


@pytest.fixture
def like_dynamo(dynamo_client):
    yield LikeDynamo(dynamo_client)


def test_parse_pk(like_dynamo):
    pk = {
        'partitionKey': 'like/lbuid/pid',
        'sortKey': '-',
    }
    liked_by_user_id, post_id = like_dynamo.parse_pk(pk)
    assert liked_by_user_id == 'lbuid'
    assert post_id == 'pid'


def test_transact_add_like(like_dynamo):
    liked_by_user_id = 'luid'
    like_status = LikeStatus.ONYMOUSLY_LIKED
    post_id = 'pid'
    post_item = {
        'postId': post_id,
        'postedByUserId': 'pbuid',
    }

    # verify no already in db
    assert like_dynamo.get_like(liked_by_user_id, post_id) is None

    # add the like to the DB
    now = datetime.utcnow()
    transact = like_dynamo.transact_add_like(liked_by_user_id, post_item, like_status, now=now)
    like_dynamo.client.transact_write_items([transact])

    # verify it exists and has the correct format
    like_item = like_dynamo.get_like(liked_by_user_id, post_id)
    liked_at_str = now.isoformat() + 'Z'
    assert like_item == {
        'schemaVersion': 1,
        'partitionKey': 'like/luid/pid',
        'sortKey': '-',
        'gsiA1PartitionKey': 'like/luid',
        'gsiA1SortKey': 'ONYMOUSLY_LIKED/' + liked_at_str,
        'gsiA2PartitionKey': 'like/pid',
        'gsiA2SortKey': 'ONYMOUSLY_LIKED/' + liked_at_str,
        'gsiK2PartitionKey': 'like/pbuid',
        'gsiK2SortKey': 'luid',
        'likedByUserId': 'luid',
        'likeStatus': 'ONYMOUSLY_LIKED',
        'likedAt': liked_at_str,
        'postId': 'pid',
    }


def test_transact_add_like_cant_relike_post(like_dynamo):
    liked_by_user_id = 'luid'
    first_like_status = LikeStatus.ANONYMOUSLY_LIKED
    second_like_status = LikeStatus.ONYMOUSLY_LIKED
    post_id = 'pid'
    post_item = {
        'postId': post_id,
        'postedByUserId': 'pbuid',
    }

    # add the like to the DB
    transact = like_dynamo.transact_add_like(liked_by_user_id, post_item, first_like_status)
    like_dynamo.client.transact_write_items([transact])

    # verify it's there with the right status
    like_item = like_dynamo.get_like(liked_by_user_id, post_id)
    assert like_item['likeStatus'] == first_like_status

    # verify we can't add another like with the same status
    transact = like_dynamo.transact_add_like(liked_by_user_id, post_item, first_like_status)
    with pytest.raises(like_dynamo.client.exceptions.ConditionalCheckFailedException):
        like_dynamo.client.transact_write_items([transact])

    # verify we can't add another like with different status
    transact = like_dynamo.transact_add_like(liked_by_user_id, post_item, second_like_status)
    with pytest.raises(like_dynamo.client.exceptions.ConditionalCheckFailedException):
        like_dynamo.client.transact_write_items([transact])


def test_transact_delete_like(like_dynamo):
    liked_by_user_id = 'luid'
    like_status = LikeStatus.ONYMOUSLY_LIKED
    post_id = 'pid'
    post_item = {
        'postId': post_id,
        'postedByUserId': 'pbuid',
    }

    # add the like to the DB
    transact = like_dynamo.transact_add_like(liked_by_user_id, post_item, like_status)
    like_dynamo.client.transact_write_items([transact])

    # verify it exists
    assert like_dynamo.get_like(liked_by_user_id, post_id) is not None

    # delete it
    transact = like_dynamo.transact_delete_like(liked_by_user_id, post_id, like_status)
    like_dynamo.client.transact_write_items([transact])

    # verify it no longer exists
    assert like_dynamo.get_like(liked_by_user_id, post_id) is None


def test_generate_of_post(like_dynamo):
    post_id = 'pid'

    # no likes on post, generate
    assert list(like_dynamo.generate_of_post(post_id)) == []

    # add one like on the post
    liked_by_user_id = 'luid1'
    post_item = {
        'postId': post_id,
        'postedByUserId': 'pbuid',
    }
    transact = like_dynamo.transact_add_like(liked_by_user_id, post_item, LikeStatus.ONYMOUSLY_LIKED)
    like_dynamo.client.transact_write_items([transact])

    # generate & check
    like_items = like_dynamo.generate_of_post(post_id)
    assert [(li['likedByUserId'], li['postId']) for li in like_items] == [('luid1', 'pid')]

    # add a like on a different post, same users
    liked_by_user_id = 'luid1'
    post_item = {
        'postId': 'otherpid',
        'postedByUserId': 'pbuid',
    }
    transact = like_dynamo.transact_add_like(liked_by_user_id, post_item, LikeStatus.ONYMOUSLY_LIKED)
    like_dynamo.client.transact_write_items([transact])

    # generate & check
    like_items = like_dynamo.generate_of_post(post_id)
    assert [(li['likedByUserId'], li['postId']) for li in like_items] == [('luid1', 'pid')]

    # add another like on the post
    liked_by_user_id = 'luid2'
    post_item = {
        'postId': post_id,
        'postedByUserId': 'pbuid',
    }
    transact = like_dynamo.transact_add_like(liked_by_user_id, post_item, LikeStatus.ONYMOUSLY_LIKED)
    like_dynamo.client.transact_write_items([transact])

    # generate & check
    like_items = like_dynamo.generate_of_post(post_id)
    liked_by_and_post_ids = sorted([(li['likedByUserId'], li['postId']) for li in like_items])
    assert liked_by_and_post_ids == [('luid1', 'pid'), ('luid2', 'pid')]


def test_generate_by_liked_by(like_dynamo):
    liked_by_user_id = 'luid'

    # no likes on post, generate
    assert list(like_dynamo.generate_by_liked_by(liked_by_user_id)) == []

    # add one like by that user
    post_item = {
        'postId': 'pid1',
        'postedByUserId': 'pbuid',
    }
    transact = like_dynamo.transact_add_like(liked_by_user_id, post_item, LikeStatus.ONYMOUSLY_LIKED)
    like_dynamo.client.transact_write_items([transact])

    # generate & check
    like_items = like_dynamo.generate_by_liked_by(liked_by_user_id)
    assert [(li['likedByUserId'], li['postId']) for li in like_items] == [('luid', 'pid1')]

    # add another like on that post by a different user
    transact = like_dynamo.transact_add_like('luidother', post_item, LikeStatus.ONYMOUSLY_LIKED)
    like_dynamo.client.transact_write_items([transact])

    # generate & check
    like_items = like_dynamo.generate_by_liked_by(liked_by_user_id)
    assert [(li['likedByUserId'], li['postId']) for li in like_items] == [('luid', 'pid1')]

    # add another like by that user
    post_item = {
        'postId': 'pid2',
        'postedByUserId': 'pbuid2',
    }
    transact = like_dynamo.transact_add_like(liked_by_user_id, post_item, LikeStatus.ONYMOUSLY_LIKED)
    like_dynamo.client.transact_write_items([transact])

    # generate & check
    like_items = like_dynamo.generate_by_liked_by(liked_by_user_id)
    liked_by_and_post_ids = sorted([(li['likedByUserId'], li['postId']) for li in like_items])
    assert liked_by_and_post_ids == [('luid', 'pid1'), ('luid', 'pid2')]


def test_generate_pks_by_liked_by_for_posted_by(like_dynamo):
    liked_by_user_id = 'luid'
    posted_by_user_id = 'pbuid'

    # no likes on post, generate
    assert list(like_dynamo.generate_pks_by_liked_by_for_posted_by(liked_by_user_id, posted_by_user_id)) == []

    # add one like for that user combo
    post_item = {
        'postId': 'pid1',
        'postedByUserId': posted_by_user_id,
    }
    transact = like_dynamo.transact_add_like(liked_by_user_id, post_item, LikeStatus.ONYMOUSLY_LIKED)
    like_dynamo.client.transact_write_items([transact])

    # generate & check
    like_pks = like_dynamo.generate_pks_by_liked_by_for_posted_by(liked_by_user_id, posted_by_user_id)
    assert [like_dynamo.parse_pk(lpk) for lpk in like_pks] == [('luid', 'pid1')]

    # add one like by different user by for same post owner
    transact = like_dynamo.transact_add_like('luidother', post_item, LikeStatus.ONYMOUSLY_LIKED)
    like_dynamo.client.transact_write_items([transact])

    # generate & check
    like_pks = like_dynamo.generate_pks_by_liked_by_for_posted_by(liked_by_user_id, posted_by_user_id)
    assert [like_dynamo.parse_pk(lpk) for lpk in like_pks] == [('luid', 'pid1')]

    # add one like by same user by for a different post owner
    post_item = {
        'postId': 'pid2',
        'postedByUserId': 'pbuid1',
    }
    transact = like_dynamo.transact_add_like(liked_by_user_id, post_item, LikeStatus.ONYMOUSLY_LIKED)
    like_dynamo.client.transact_write_items([transact])

    # generate & check
    like_pks = like_dynamo.generate_pks_by_liked_by_for_posted_by(liked_by_user_id, posted_by_user_id)
    assert [like_dynamo.parse_pk(lpk) for lpk in like_pks] == [('luid', 'pid1')]

    # add one like for that user combo
    post_item = {
        'postId': 'pid4',
        'postedByUserId': posted_by_user_id,
    }
    transact = like_dynamo.transact_add_like(liked_by_user_id, post_item, LikeStatus.ONYMOUSLY_LIKED)
    like_dynamo.client.transact_write_items([transact])

    # generate & check
    like_pks = like_dynamo.generate_pks_by_liked_by_for_posted_by(liked_by_user_id, posted_by_user_id)
    assert sorted([like_dynamo.parse_pk(lpk) for lpk in like_pks]) == [('luid', 'pid1'), ('luid', 'pid4')]
