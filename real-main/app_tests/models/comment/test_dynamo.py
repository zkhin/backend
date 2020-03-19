import pendulum
import pytest

from app.models.comment.dynamo import CommentDynamo
from app.models.comment.exceptions import CommentException


@pytest.fixture
def comment_dynamo(dynamo_client):
    yield CommentDynamo(dynamo_client)


def test_transact_add_comment(comment_dynamo):
    comment_id = 'cid'
    post_id = 'pid'
    user_id = 'uid'
    text = 'text @dog'
    text_tags = [{'tag': '@dog', 'userId': 'duid'}]
    now = pendulum.now('utc')

    # add the comment to the DB
    transact = comment_dynamo.transact_add_comment(comment_id, post_id, user_id, text, text_tags, now)
    comment_dynamo.client.transact_write_items([transact])

    # retrieve the comment and verify the format is as we expect
    comment_item = comment_dynamo.get_comment(comment_id)
    commented_at_str = now.to_iso8601_string()
    assert comment_item == {
        'partitionKey': 'comment/cid',
        'sortKey': '-',
        'schemaVersion': 0,
        'gsiA1PartitionKey': 'comment/pid',
        'gsiA1SortKey': commented_at_str,
        'gsiA2PartitionKey': 'comment/uid',
        'gsiA2SortKey': commented_at_str,
        'commentId': 'cid',
        'postId': 'pid',
        'userId': 'uid',
        'text': text,
        'textTags': text_tags,
        'commentedAt': commented_at_str,
    }


def test_cant_transact_add_comment_same_comment_id(comment_dynamo):
    comment_id = 'cid'
    post_id = 'pid'
    user_id = 'uid'
    text = 'lore'
    text_tags = []

    # add a comment with that comment id
    transact = comment_dynamo.transact_add_comment(comment_id, post_id, user_id, text, text_tags)
    comment_dynamo.client.transact_write_items([transact])

    # verify we can't add another comment with the same id
    with pytest.raises(comment_dynamo.client.exceptions.ConditionalCheckFailedException):
        comment_dynamo.client.transact_write_items([transact])


def test_cant_transact_delete_comment_doesnt_exist(comment_dynamo):
    comment_id = 'dne-cid'
    transact = comment_dynamo.transact_delete_comment(comment_id)
    with pytest.raises(comment_dynamo.client.exceptions.ConditionalCheckFailedException):
        comment_dynamo.client.transact_write_items([transact])


@pytest.mark.xfail(strict=True, reason='https://github.com/spulec/moto/issues/2424')
def test_add_comment_view_failures(comment_dynamo):
    comment_id = 'cid'
    post_id = 'pid'
    user_id = 'uid'
    viewed_at = pendulum.now('utc')

    # verify can't add view if comment doesn't exist
    with pytest.raises(CommentException, match='does not exist'):
        comment_dynamo.add_comment_view(comment_id, user_id, viewed_at)

    # add the comment
    transact = comment_dynamo.transact_add_comment(comment_id, post_id, user_id, 'lore', [])
    comment_dynamo.client.transact_write_items([transact])

    # verify can't add a view as author of the comment
    with pytest.raises(CommentException, match='viewer is author'):
        comment_dynamo.add_comment_view(comment_id, user_id, viewed_at)

    # add a view as another user
    other_user_id = 'ouid'
    comment_dynamo.add_comment_view(comment_id, other_user_id, viewed_at)
    assert comment_dynamo.get_comment_view(comment_id, other_user_id)

    # can't view the same comment twice
    with pytest.raises(CommentException, match='view already exists'):
        comment_dynamo.add_comment_view(comment_id, other_user_id, viewed_at)


def test_add_comment_view(comment_dynamo):
    # add the comment
    post_id = 'pid'
    comment_id = 'cid'
    user_id = 'uid'
    transact = comment_dynamo.transact_add_comment(comment_id, post_id, user_id, 'lore', [])
    comment_dynamo.client.transact_write_items([transact])

    # check no view exists for another user
    other_user_id = 'ouid'
    assert comment_dynamo.get_comment_view(comment_id, other_user_id) is None

    # add a view as another user
    viewed_at = pendulum.now('utc')
    comment_dynamo.add_comment_view(comment_id, other_user_id, viewed_at)

    # verify that view has right form in db
    item = comment_dynamo.get_comment_view(comment_id, other_user_id)
    assert item == {
        'partitionKey': 'commentView/cid/ouid',
        'sortKey': '-',
        'schemaVersion': 0,
        'gsiK1PartitionKey': 'commentView/cid',
        'gsiK1SortKey': viewed_at.to_iso8601_string(),
        'commentId': 'cid',
        'userId': 'ouid',
        'viewedAt': viewed_at.to_iso8601_string(),
    }


def test_transact_delete_comment(comment_dynamo):
    comment_id = 'cid'
    post_id = 'pid'
    user_id = 'uid'
    text = 'lore'
    text_tags = []

    # add the comment
    transact = comment_dynamo.transact_add_comment(comment_id, post_id, user_id, text, text_tags)
    comment_dynamo.client.transact_write_items([transact])

    # verify we can see the comment in the DB
    comment_item = comment_dynamo.get_comment(comment_id)
    assert comment_item['commentId'] == comment_id

    # delete the comment
    transact = comment_dynamo.transact_delete_comment(comment_id)
    comment_dynamo.client.transact_write_items([transact])

    # verify the comment is no longer in the db
    assert comment_dynamo.get_comment(comment_id) is None


def test_generate_by_post(comment_dynamo):
    post_id = 'pid'

    # add a comment on an unrelated post
    transact = comment_dynamo.transact_add_comment('coid', 'poid', 'uiod', 't', [])
    comment_dynamo.client.transact_write_items([transact])

    # post has no comments, generate them
    assert list(comment_dynamo.generate_by_post(post_id)) == []

    # add two comments to that post
    comment_id_1 = 'cid1'
    comment_id_2 = 'cid2'
    transacts = [
        comment_dynamo.transact_add_comment(comment_id_1, post_id, 'uid1', 't', []),
        comment_dynamo.transact_add_comment(comment_id_2, post_id, 'uid1', 't', []),
    ]
    comment_dynamo.client.transact_write_items(transacts)

    # generate comments, verify order
    comment_items = list(comment_dynamo.generate_by_post(post_id))
    assert len(comment_items) == 2
    assert comment_items[0]['commentId'] == comment_id_1
    assert comment_items[1]['commentId'] == comment_id_2


def test_generate_by_user(comment_dynamo):
    user_id = 'uid'

    # add a comment by an unrelated user
    transact = comment_dynamo.transact_add_comment('coid', 'poid', 'uiod', 't', [])
    comment_dynamo.client.transact_write_items([transact])

    # user has no comments, generate them
    assert list(comment_dynamo.generate_by_user(user_id)) == []

    # add two comments by that user
    comment_id_1 = 'cid1'
    comment_id_2 = 'cid2'
    transacts = [
        comment_dynamo.transact_add_comment(comment_id_1, 'pid1', user_id, 't', []),
        comment_dynamo.transact_add_comment(comment_id_2, 'pid2', user_id, 't', []),
    ]
    comment_dynamo.client.transact_write_items(transacts)

    # generate comments, verify order
    comment_items = list(comment_dynamo.generate_by_user(user_id))
    assert len(comment_items) == 2
    assert comment_items[0]['commentId'] == comment_id_1
    assert comment_items[1]['commentId'] == comment_id_2


def test_generate_comment_view_keys_by_comment(comment_dynamo):
    comment_id = 'cid'

    # test generate for comment that doesn't exist
    keys = list(comment_dynamo.generate_comment_view_keys_by_comment(comment_id))
    assert keys == []

    # add the comment
    post_id = 'pid'
    user_id = 'uid'
    transact = comment_dynamo.transact_add_comment(comment_id, post_id, user_id, 'ipsum', [])
    comment_dynamo.client.transact_write_items([transact])

    # test generate views comment that exists with no views
    keys = list(comment_dynamo.generate_comment_view_keys_by_comment(comment_id))
    assert keys == []

    # add a comment view
    other_user_id_1 = 'ouid1'
    viewed_at = pendulum.now('utc')
    comment_dynamo.add_comment_view(comment_id, other_user_id_1, viewed_at)
    comment_1_key = comment_dynamo.get_comment_view_pk(comment_id, other_user_id_1)

    # test we generate that user in our comment views
    keys = list(comment_dynamo.generate_comment_view_keys_by_comment(comment_id))
    assert keys == [comment_1_key]

    # add another comment view
    other_user_id_2 = 'ouid2'
    viewed_at = pendulum.now('utc')
    comment_dynamo.add_comment_view(comment_id, other_user_id_2, viewed_at)
    comment_2_key = comment_dynamo.get_comment_view_pk(comment_id, other_user_id_2)

    # test we generate both users in our comment views
    keys = list(comment_dynamo.generate_comment_view_keys_by_comment(comment_id))
    assert keys == [comment_1_key, comment_2_key]
