from datetime import datetime

import pytest

from app.models.comment.dynamo import CommentDynamo


@pytest.fixture
def comment_dynamo(dynamo_client):
    yield CommentDynamo(dynamo_client)


def test_transact_add_comment(comment_dynamo):
    comment_id = 'cid'
    post_id = 'pid'
    user_id = 'uid'
    text = 'text @dog'
    text_tags = [{'tag': '@dog', 'userId': 'duid'}]
    now = datetime.utcnow()

    # add the comment to the DB
    transact = comment_dynamo.transact_add_comment(comment_id, post_id, user_id, text, text_tags, now)
    comment_dynamo.client.transact_write_items([transact])

    # retrieve the comment and verify the format is as we expect
    comment_item = comment_dynamo.get_comment(comment_id)
    commented_at_str = now.isoformat() + 'Z'
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


@pytest.mark.xfail(reason='https://github.com/spulec/moto/issues/1071')
def test_cant_transact_delete_comment_doesnt_exist(comment_dynamo):
    comment_id = 'dne-cid'
    transact = comment_dynamo.transact_delete_comment(comment_id)
    with pytest.raises(comment_dynamo.client.exceptions.ConditionalCheckFailedException):
        comment_dynamo.client.transact_write_items([transact])


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
