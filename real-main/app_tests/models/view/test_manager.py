import logging
from unittest.mock import Mock, call

import pendulum
import pytest

from app.models.post.enums import PostStatus, PostType


@pytest.fixture
def user(user_manager):
    yield user_manager.create_cognito_only_user('pbuid', 'pbUname')


@pytest.fixture
def user2(user_manager):
    yield user_manager.create_cognito_only_user('pbuid2', 'pbUname2')


@pytest.fixture
def user3(user_manager):
    yield user_manager.create_cognito_only_user('pbuid3', 'pbUname3')


@pytest.fixture
def posts(post_manager, user):
    post1 = post_manager.add_post(user.id, 'pid1', PostType.TEXT_ONLY, text='t')
    post2 = post_manager.add_post(user.id, 'pid2', PostType.TEXT_ONLY, text='t')
    yield (post1, post2)


@pytest.fixture
def comment(comment_manager, posts, user):
    yield comment_manager.add_comment('cmid', posts[0].id, user.id, 'witty comment')


@pytest.fixture
def chat_message(chat_manager, chat_message_manager, user, user2):
    chat = chat_manager.add_direct_chat('chid', user.id, user2.id)
    yield chat_message_manager.add_chat_message('mid', 'heyya', chat.id, user.id)


def test_delete_views(view_manager, posts):
    post1, post2 = posts
    partition_key_1 = post1.item['partitionKey']
    partition_key_2 = post2.item['partitionKey']
    vb_user_id_1 = 'vuid1'
    vb_user_id_2 = 'vuid2'

    # check that a none-to-delete does not error out
    view_manager.delete_views(partition_key_1)

    # views by each user on each of the two posts
    view_manager.record_views('post', [post1.id, post2.id], vb_user_id_1)
    view_manager.record_views('post', [post1.id, post2.id], vb_user_id_2)

    # check we see all those views in the DB
    assert view_manager.dynamo.get_view(partition_key_1, vb_user_id_1)
    assert view_manager.dynamo.get_view(partition_key_1, vb_user_id_2)
    assert view_manager.dynamo.get_view(partition_key_2, vb_user_id_1)
    assert view_manager.dynamo.get_view(partition_key_2, vb_user_id_2)

    # delete all views on one post, check again
    view_manager.delete_views(partition_key_1)
    assert view_manager.dynamo.get_view(partition_key_1, vb_user_id_1) is None
    assert view_manager.dynamo.get_view(partition_key_1, vb_user_id_2) is None
    assert view_manager.dynamo.get_view(partition_key_2, vb_user_id_1)
    assert view_manager.dynamo.get_view(partition_key_2, vb_user_id_2)

    # delete all views on the other post, check again
    view_manager.delete_views(partition_key_2)
    assert view_manager.dynamo.get_view(partition_key_2, vb_user_id_1) is None
    assert view_manager.dynamo.get_view(partition_key_2, vb_user_id_2) is None


def test_record_views(view_manager):
    # catch any calls to 'record_view'
    view_manager.record_view = Mock()

    # call with no post_ids
    viewed_at = pendulum.now('utc')
    view_manager.record_views('itype', [], 'vuid', viewed_at)
    assert view_manager.record_view.mock_calls == []

    # call with some post ids
    view_manager.record_views('itype', ['pid1', 'pid2', 'pid1'], 'vuid', viewed_at)
    assert view_manager.record_view.mock_calls == [
        call('itype', 'pid1', 'vuid', 2, viewed_at),
        call('itype', 'pid2', 'vuid', 1, viewed_at),
    ]


def test_cant_record_view_bad_item_type(view_manager):
    item_type = 'nope nope'
    with pytest.raises(Exception, match='item type'):
        view_manager.record_view(item_type, None, None, None, None)


def test_record_view_chat_message(view_manager, chat_message, user2):
    # check there is no view
    assert view_manager.get_viewed_status(chat_message, user2.id) == 'NOT_VIEWED'

    # add a view, check that it worked
    view_manager.record_view('chat_message', chat_message.id, user2.id, 2, pendulum.now('utc'))
    assert view_manager.get_viewed_status(chat_message, user2.id) == 'VIEWED'


def test_record_view_comment(view_manager, comment, user2):
    # check there is no view
    assert view_manager.get_viewed_status(comment, user2.id) == 'NOT_VIEWED'

    # add a view, check that it worked
    view_manager.record_view('comment', comment.id, user2.id, 2, pendulum.now('utc'))
    assert view_manager.get_viewed_status(comment, user2.id) == 'VIEWED'


def test_record_view_comment_clears_new_comment_activity(view_manager, comment_manager, posts, user, user2, user3):
    post, _ = posts

    # add a comment by a different user to get some activity on the post
    comment = comment_manager.add_comment('cmid2', post.id, user2.id, 'witty comment')
    post.refresh_item()
    assert post.item.get('hasNewCommentActivity', False) is True

    # record a view of that comment by a user that is not the post owner
    view_manager.record_view('comment', comment.id, user3.id, 2, pendulum.now('utc'))

    # verify the post still has comment activity
    post.refresh_item()
    assert post.item.get('hasNewCommentActivity', False) is True

    # record a view of that comment by the post owner
    view_manager.record_view('comment', comment.id, user.id, 2, pendulum.now('utc'))

    # verify the post now has no comment activity
    post.refresh_item()
    assert post.item.get('hasNewCommentActivity', False) is False


def test_record_view_post_not_completed(view_manager, posts, caplog, post_manager, user_manager, trending_manager):
    user_id = 'vuid'

    # set up an archived post
    post = posts[0]
    post.archive()

    # try to record a view on it
    with caplog.at_level(logging.WARNING):
        # fails with logged warning
        view_manager.record_view('post', post.id, user_id, 3, pendulum.now('utc'))

    # check the logging
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == 'WARNING'
    assert f'`{user_id}`' in caplog.records[0].msg
    assert f'`{post.id}`' in caplog.records[0].msg
    assert 'COMPLETED' in caplog.records[0].msg

    # check the viewedByCounts and the trending indexes did not change
    posted_by_user_id = post.item['postedByUserId']
    assert post_manager.dynamo.get_post(post.id).get('viewedByCount', 0) == 0
    assert user_manager.dynamo.get_user(posted_by_user_id).get('postViewedByCount', 0) == 0
    assert trending_manager.dynamo.get_trending(post.id) is None
    assert trending_manager.dynamo.get_trending(posted_by_user_id) is None


def test_record_view_post_does_not_exist(view_manager, caplog):
    user_id = 'vuid'
    post_id = 'pid-dne'

    with caplog.at_level(logging.WARNING):
        # fails with logged warning
        view_manager.record_view('post', post_id, user_id, 3, pendulum.now('utc'))

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == 'WARNING'
    assert f'`{user_id}`' in caplog.records[0].msg
    assert f'`{post_id}`' in caplog.records[0].msg
    assert 'DNE' in caplog.records[0].msg


def test_record_view_post_success(view_manager, posts, post_manager, user_manager, trending_manager):
    post, _ = posts
    viewed_by_user_id = 'vuid'

    # check there is no post view yet recorded for this user on this post
    assert view_manager.get_viewed_status(post, viewed_by_user_id) == 'NOT_VIEWED'
    assert post_manager.dynamo.get_post(post.id).get('viewedByCount', 0) == 0
    assert user_manager.dynamo.get_user(post.user_id).get('postViewedByCount', 0) == 0
    assert trending_manager.dynamo.get_trending(post.id) is None
    assert trending_manager.dynamo.get_trending(post.user_id) is None

    # record the first post view
    view_manager.record_view('post', post.id, viewed_by_user_id, 2, pendulum.now('utc'))
    assert view_manager.get_viewed_status(post, viewed_by_user_id) == 'VIEWED'

    # check the viewedByCounts and the trending indexes all incremented
    assert post_manager.dynamo.get_post(post.id).get('viewedByCount', 0) == 1
    assert user_manager.dynamo.get_user(post.user_id).get('postViewedByCount', 0) == 1
    assert trending_manager.dynamo.get_trending(post.id).get('gsiK3SortKey', 0) == 1
    assert trending_manager.dynamo.get_trending(post.user_id).get('gsiK3SortKey', 0) == 1

    # record a second post view for this user on this post
    view_manager.record_view('post', post.id, viewed_by_user_id, 1, pendulum.now('utc'))
    assert view_manager.get_viewed_status(post, viewed_by_user_id) == 'VIEWED'

    # check the viewedByCounts and the trending indexes all did not change
    assert post_manager.dynamo.get_post(post.id).get('viewedByCount', 0) == 1
    assert user_manager.dynamo.get_user(post.user_id).get('postViewedByCount', 0) == 1
    assert trending_manager.dynamo.get_trending(post.id).get('gsiK3SortKey', 0) == 1
    assert trending_manager.dynamo.get_trending(post.user_id).get('gsiK3SortKey', 0) == 1


def test_record_view_by_post_owner_not_recorded(view_manager, posts, post_manager, user_manager, trending_manager):
    post, _ = posts

    # author should always show as viewed, but there should be no view record in the db
    assert view_manager.get_viewed_status(post, post.user_id) == 'VIEWED'
    assert view_manager.dynamo.get_view(post.item['partitionKey'], post.user_id) is None

    # check there is no post view yet recorded for this user on this post
    assert post_manager.dynamo.get_post(post.id).get('viewedByCount', 0) == 0
    assert user_manager.dynamo.get_user(post.user_id).get('postViewedByCount', 0) == 0
    assert trending_manager.dynamo.get_trending(post.id) is None
    assert trending_manager.dynamo.get_trending(post.user_id) is None

    # record the first post view, should be ignored
    view_manager.record_view('post', post.id, post.user_id, 1, pendulum.now('utc'))
    assert view_manager.get_viewed_status(post, post.user_id) == 'VIEWED'
    assert view_manager.dynamo.get_view(post.item['partitionKey'], post.user_id) is None

    # check nothing changed in the DB
    assert post_manager.dynamo.get_post(post.id).get('viewedByCount', 0) == 0
    assert user_manager.dynamo.get_user(post.user_id).get('postViewedByCount', 0) == 0
    assert trending_manager.dynamo.get_trending(post.id) is None
    assert trending_manager.dynamo.get_trending(post.user_id) is None


def test_record_view_for_non_original_post(view_manager, user, posts, post_manager, user_manager, trending_manager):
    org_post, non_org_post = posts

    # hack to get these text-only posts to have an original. Set it back to pending and then completed
    transact_set_post_status = post_manager.dynamo.transact_set_post_status
    post_manager.dynamo.client.transact_write_items([
        transact_set_post_status(non_org_post.item, PostStatus.PENDING),
    ])
    post_manager.dynamo.client.transact_write_items([
        transact_set_post_status(non_org_post.item, PostStatus.COMPLETED, original_post_id=org_post.id),
    ])
    non_org_post.refresh_item()

    viewed_by_user_id = 'vuid'
    # check there is no post view yet recorded for this user on either post
    assert view_manager.get_viewed_status(org_post, viewed_by_user_id) == 'NOT_VIEWED'
    assert view_manager.get_viewed_status(non_org_post, viewed_by_user_id) == 'NOT_VIEWED'
    assert post_manager.dynamo.get_post(org_post.id).get('viewedByCount', 0) == 0
    assert post_manager.dynamo.get_post(non_org_post.id).get('viewedByCount', 0) == 0
    assert user_manager.dynamo.get_user(user.id).get('postViewedByCount', 0) == 0
    assert trending_manager.dynamo.get_trending(org_post.id) is None
    assert trending_manager.dynamo.get_trending(non_org_post.id) is None
    assert trending_manager.dynamo.get_trending(user.id) is None

    # record a first post view on the non-original post
    view_count = 3
    viewed_at = pendulum.now('utc')
    viewed_at_str = viewed_at.to_iso8601_string()
    view_manager.record_view('post', non_org_post.id, viewed_by_user_id, view_count, viewed_at)

    # check two post view items were created, one for each post
    assert view_manager.get_viewed_status(org_post, viewed_by_user_id) == 'VIEWED'
    assert view_manager.get_viewed_status(non_org_post, viewed_by_user_id) == 'VIEWED'
    item = view_manager.dynamo.get_view(org_post.item['partitionKey'], viewed_by_user_id)
    assert item['viewCount'] == view_count
    assert item['firstViewedAt'] == viewed_at_str
    assert item['lastViewedAt'] == viewed_at_str
    non_org_item = view_manager.dynamo.get_view(non_org_post.item['partitionKey'], viewed_by_user_id)
    assert non_org_item['viewCount'] == view_count
    assert non_org_item['firstViewedAt'] == viewed_at_str
    assert non_org_item['lastViewedAt'] == viewed_at_str

    # check the viewedByCounts
    assert post_manager.dynamo.get_post(org_post.id).get('viewedByCount', 0) == 1
    assert post_manager.dynamo.get_post(non_org_post.id).get('viewedByCount', 0) == 1
    assert user_manager.dynamo.get_user(user.id).get('postViewedByCount', 0) == 2

    # check the original post made it into the trending indexes, and then non-original did not
    assert trending_manager.dynamo.get_trending(org_post.id).get('gsiK3SortKey', 0) == 1
    assert trending_manager.dynamo.get_trending(non_org_post.id) is None
    assert trending_manager.dynamo.get_trending(user.id).get('gsiK3SortKey', 0) == 1

    # now record a view directly on the original post
    new_view_count = 5
    new_viewed_at = pendulum.now('utc')
    new_viewed_at_str = new_viewed_at.to_iso8601_string()
    view_manager.record_view('post', org_post.id, viewed_by_user_id, new_view_count, new_viewed_at)

    # check the post view item for the original post was incremented correctly
    assert view_manager.get_viewed_status(org_post, viewed_by_user_id) == 'VIEWED'
    item = view_manager.dynamo.get_view(org_post.item['partitionKey'], viewed_by_user_id)
    assert item['viewCount'] == view_count + new_view_count
    assert item['firstViewedAt'] == viewed_at_str
    assert item['lastViewedAt'] == new_viewed_at_str

    # no change for the non-original post
    assert view_manager.dynamo.get_view(non_org_post.item['partitionKey'], viewed_by_user_id) == non_org_item

    # check no change to viewedByCounts, nor trending indexes
    assert post_manager.dynamo.get_post(org_post.id).get('viewedByCount', 0) == 1
    assert post_manager.dynamo.get_post(non_org_post.id).get('viewedByCount', 0) == 1
    assert user_manager.dynamo.get_user(user.id).get('postViewedByCount', 0) == 2
    assert trending_manager.dynamo.get_trending(org_post.id).get('gsiK3SortKey', 0) == 1
    assert trending_manager.dynamo.get_trending(non_org_post.id) is None
    assert trending_manager.dynamo.get_trending(user.id).get('gsiK3SortKey', 0) == 1
