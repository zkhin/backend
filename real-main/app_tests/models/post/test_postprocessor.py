import logging
from uuid import uuid4

import pendulum
import pytest

from app.models.card.specs import CommentCardSpec
from app.models.post.enums import PostStatus, PostType


@pytest.fixture
def post_postprocessor(post_manager):
    yield post_manager.postprocessor


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


user2 = user


@pytest.fixture
def post(post_manager, user):
    yield post_manager.add_post(user, str(uuid4()), PostType.TEXT_ONLY, text='go go')


def test_run_keep_card_insync(post_postprocessor, post, card_manager):
    pk, sk = post.item['partitionKey'], post.item['sortKey']

    # verify starting state
    card_spec = CommentCardSpec(post.user_id, post.id)
    assert card_manager.get_card(card_spec.card_id) is None

    # no change to our field
    old_item = post.item
    new_item = {**old_item, 'unrelated': 42}
    post_postprocessor.run(pk, sk, old_item, new_item)
    assert card_manager.get_card(card_spec.card_id) is None

    # add card
    old_item = new_item
    new_item = {**old_item, 'commentsUnviewedCount': 1}
    post_postprocessor.run(pk, sk, old_item, new_item)
    card = card_manager.get_card(card_spec.card_id)
    assert card.id == card_spec.card_id

    # change card title
    old_item = new_item
    new_item = {**old_item, 'commentsUnviewedCount': 2}
    post_postprocessor.run(pk, sk, old_item, new_item)
    new_card = card_manager.get_card(card_spec.card_id)
    assert new_card.id == card_spec.card_id
    assert new_card.item['title'] != card.item['title']

    # delete card
    old_item = new_item
    new_item = {**old_item, 'commentsUnviewedCount': 0}
    post_postprocessor.run(pk, sk, old_item, new_item)
    assert card_manager.get_card(card_spec.card_id) is None


def test_comment_added(post_postprocessor, post, user, user2):
    # verify starting state
    post.refresh_item()
    assert 'commentCount' not in post.item
    assert 'commentsUnviewedCount' not in post.item
    assert 'gsiA3PartitionKey' not in post.item
    assert 'gsiA3SortKey' not in post.item

    # postprocess a comment by the owner, which is already viewed
    post_postprocessor.comment_added(post.id, user.id, 'unused')
    post.refresh_item()
    assert post.item['commentCount'] == 1
    assert 'commentsUnviewedCount' not in post.item
    assert 'gsiA3PartitionKey' not in post.item
    assert 'gsiA3SortKey' not in post.item

    # postprocess a comment by other, which has not yet been viewed
    now = pendulum.now('utc')
    post_postprocessor.comment_added(post.id, user2.id, now)
    post.refresh_item()
    assert post.item['commentCount'] == 2
    assert post.item['commentsUnviewedCount'] == 1
    assert post.item['gsiA3PartitionKey'].split('/') == ['post', user.id]
    assert pendulum.parse(post.item['gsiA3SortKey']) == now

    # postprocess another comment by other, which has not yet been viewed
    now = pendulum.now('utc')
    post_postprocessor.comment_added(post.id, user2.id, now)
    post.refresh_item()
    assert post.item['commentCount'] == 3
    assert post.item['commentsUnviewedCount'] == 2
    assert post.item['gsiA3PartitionKey'].split('/') == ['post', user.id]
    assert pendulum.parse(post.item['gsiA3SortKey']) == now


def test_comment_deleted(post_postprocessor, post, user2, caplog):
    # postprocess an two adds to increment counts, and verify starting state
    post_postprocessor.comment_added(post.id, user2.id, pendulum.now('utc'))
    post_postprocessor.comment_added(post.id, user2.id, pendulum.now('utc'))
    post.refresh_item()
    assert post.item['commentCount'] == 2
    assert post.item['commentsUnviewedCount'] == 2

    # postprocess a deleted comment, verify counts drop as expected
    post_postprocessor.comment_deleted(post.id, str(uuid4()), user2.id, pendulum.now('utc'))
    post.refresh_item()
    assert post.item['commentCount'] == 1
    assert post.item['commentsUnviewedCount'] == 1

    # postprocess a deleted comment, verify counts drop as expected
    post_postprocessor.comment_deleted(post.id, str(uuid4()), user2.id, pendulum.now('utc'))
    post.refresh_item()
    assert post.item['commentCount'] == 0
    assert post.item['commentsUnviewedCount'] == 0

    # postprocess a deleted comment, verify fails softly and final state
    with caplog.at_level(logging.WARNING):
        post_postprocessor.comment_deleted(post.id, str(uuid4()), user2.id, pendulum.now('utc'))
    assert len(caplog.records) == 2
    assert 'Failed to decrement commentCount' in caplog.records[0].msg
    assert 'Failed to decrement commentsUnviewedCount' in caplog.records[1].msg
    assert post.id in caplog.records[0].msg
    assert post.id in caplog.records[1].msg
    post.refresh_item()
    assert post.item['commentCount'] == 0
    assert post.item['commentsUnviewedCount'] == 0


def test_comment_deleted_with_comment_views(post_postprocessor, post, user, user2, caplog, comment_manager):
    # post owner adds a comment, other user adds two comments
    comment1 = comment_manager.add_comment(str(uuid4()), post.id, user.id, 'lore ipsum')
    comment2 = comment_manager.add_comment(str(uuid4()), post.id, user2.id, 'lore ipsum')
    comment3 = comment_manager.add_comment(str(uuid4()), post.id, user2.id, 'lore ipsum')
    post_postprocessor.comment_added(post.id, user.id, comment1.created_at)
    post_postprocessor.comment_added(post.id, user2.id, comment2.created_at)
    post_postprocessor.comment_added(post.id, user2.id, comment3.created_at)

    # post owner views one of their two comments
    comment2.record_view_count(user.id, 1)
    post_postprocessor.comment_view_added(post.id, user.id)

    # check starting state
    post.refresh_item()
    assert post.item['commentCount'] == 3
    assert post.item['commentsUnviewedCount'] == 1

    # other user deletes their viewed comment, check state
    post_postprocessor.comment_deleted(post.id, comment2.id, user2.id, comment2.created_at)
    post.refresh_item()
    assert post.item['commentCount'] == 2
    assert post.item['commentsUnviewedCount'] == 1

    # post owner deletes their own comment, check state
    post_postprocessor.comment_deleted(post.id, comment1.id, user.id, comment1.created_at)
    post.refresh_item()
    assert post.item['commentCount'] == 1
    assert post.item['commentsUnviewedCount'] == 1

    # other user deletes their unviewed comment, check state
    post_postprocessor.comment_deleted(post.id, comment3.id, user2.id, comment3.created_at)
    post.refresh_item()
    assert post.item['commentCount'] == 0
    assert post.item['commentsUnviewedCount'] == 0


def test_comment_deleted_with_post_views(
    post_postprocessor, post, user, user2, caplog, comment_manager, post_manager
):
    # post owner adds a acomment
    comment1 = comment_manager.add_comment(str(uuid4()), post.id, user.id, 'lore ipsum')
    post_postprocessor.comment_added(post.id, user.id, comment1.created_at)

    # other user adds a comment
    comment2 = comment_manager.add_comment(str(uuid4()), post.id, user2.id, 'lore ipsum')
    post_postprocessor.comment_added(post.id, user2.id, comment2.created_at)

    # post owner views all the comments
    post_manager.record_views([post.id], user.id)

    # other user adds another comment
    comment3 = comment_manager.add_comment(str(uuid4()), post.id, user2.id, 'lore ipsum')
    post_postprocessor.comment_added(post.id, user2.id, comment3.created_at)

    # other user adds another comment
    comment4 = comment_manager.add_comment(str(uuid4()), post.id, user2.id, 'lore ipsum')
    post_postprocessor.comment_added(post.id, user2.id, comment4.created_at)

    # verify starting state
    post.refresh_item()
    assert post.item['commentCount'] == 4
    assert post.item['commentsUnviewedCount'] == 2
    assert pendulum.parse(post.item['gsiA3SortKey']) == comment4.created_at

    # postprocess deleteing comment4, verify state
    post_postprocessor.comment_deleted(post.id, comment4.id, comment4.user_id, comment4.created_at)
    post.refresh_item()
    assert post.item['commentCount'] == 3
    assert post.item['commentsUnviewedCount'] == 1
    assert pendulum.parse(post.item['gsiA3SortKey']) == comment4.created_at

    # postprocess deleteing comment2, verify state
    post_postprocessor.comment_deleted(post.id, comment2.id, comment2.user_id, comment2.created_at)
    post.refresh_item()
    assert post.item['commentCount'] == 2
    assert post.item['commentsUnviewedCount'] == 1
    assert pendulum.parse(post.item['gsiA3SortKey']) == comment4.created_at

    # postprocess deleteing comment4, verify state
    post_postprocessor.comment_deleted(post.id, comment4.id, comment4.user_id, comment4.created_at)
    post.refresh_item()
    assert post.item['commentCount'] == 1
    assert post.item['commentsUnviewedCount'] == 0
    assert 'gsiA3SortKey' not in post.item

    # postprocess deleteing comment1, verify state
    post_postprocessor.comment_deleted(post.id, comment1.id, comment1.user_id, comment1.created_at)
    post.refresh_item()
    assert post.item['commentCount'] == 0
    assert post.item['commentsUnviewedCount'] == 0
    assert 'gsiA3SortKey' not in post.item


def test_comment_view_added(post_postprocessor, post, user, user2):
    # get some comment counts in there, check starting state
    post_postprocessor.comment_added(post.id, user2.id, pendulum.now('utc'))
    post_postprocessor.comment_added(post.id, user2.id, pendulum.now('utc'))
    assert post.refresh_item().item['commentsUnviewedCount'] == 2

    # postprocess a view not by the post owner, verify state
    post_postprocessor.comment_view_added(post.id, user2.id)
    assert post.refresh_item().item['commentsUnviewedCount'] == 2

    # postprocess a view by the post owner, verify state
    post_postprocessor.comment_view_added(post.id, user.id)
    assert post.refresh_item().item['commentsUnviewedCount'] == 1

    # another view by post owner
    post_postprocessor.comment_view_added(post.id, user.id)
    assert post.refresh_item().item['commentsUnviewedCount'] == 0


def test_post_flag_added(post_postprocessor, post, user2):
    # check starting state
    assert post.refresh_item().item.get('flagCount', 0) == 0

    # postprocess, verify flagCount is incremented & not force achived
    post_postprocessor.post_flag_added(post.id, user2.id)
    assert post.refresh_item().item.get('flagCount', 0) == 1
    assert post.status != PostStatus.ARCHIVED


def test_post_flag_added_force_archive_by_admin(post_postprocessor, post, user2, caplog):
    # configure and check starting state
    assert post.refresh_item().item.get('flagCount', 0) == 0
    user2.update_username(post.flag_admin_usernames[0])

    # postprocess, verify flagCount is incremented and force archived
    with caplog.at_level(logging.WARNING):
        post_postprocessor.post_flag_added(post.id, user2.id)
    assert len(caplog.records) == 1
    assert 'Force archiving post' in caplog.records[0].msg
    assert post.refresh_item().item.get('flagCount', 0) == 1
    assert post.status == PostStatus.ARCHIVED


def test_post_flag_added_force_archive_by_crowdsourced_criteria(post_postprocessor, post, user2, caplog):
    # configure and check starting state
    assert post.refresh_item().item.get('flagCount', 0) == 0
    for _ in range(6):
        post.dynamo.increment_viewed_by_count(post.id)

    # postprocess, verify flagCount is incremented and force archived
    with caplog.at_level(logging.WARNING):
        post_postprocessor.post_flag_added(post.id, user2.id)
    assert len(caplog.records) == 1
    assert 'Force archiving post' in caplog.records[0].msg
    assert post.refresh_item().item.get('flagCount', 0) == 1
    assert post.status == PostStatus.ARCHIVED


def test_post_flag_deleted(post_postprocessor, post, user2, caplog):
    # configure and check starting state
    post_postprocessor.post_flag_added(post.id, user2.id)
    assert post.refresh_item().item.get('flagCount', 0) == 1

    # postprocess, verify flagCount is decremented
    post_postprocessor.post_flag_deleted(post.id)
    assert post.refresh_item().item.get('flagCount', 0) == 0

    # postprocess again, verify fails softly
    with caplog.at_level(logging.WARNING):
        post_postprocessor.post_flag_deleted(post.id)
    assert len(caplog.records) == 1
    assert 'Failed to decrement flagCount' in caplog.records[0].msg
    assert post.refresh_item().item.get('flagCount', 0) == 0
