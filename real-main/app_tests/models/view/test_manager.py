import logging
from unittest.mock import Mock, call
import uuid

import pendulum
import pytest

from app.models.post.enums import PostStatus, PostType


@pytest.fixture
def user(user_manager, cognito_client):
    user_id = str(uuid.uuid4())
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username=user_id)
    yield user_manager.create_cognito_only_user(user_id, str(uuid.uuid4())[:8])


user2 = user
user3 = user


@pytest.fixture
def real_user(user_manager, cognito_client):
    user_id = str(uuid.uuid4())
    cognito_client.boto_client.admin_create_user(UserPoolId=cognito_client.user_pool_id, Username=user_id)
    yield user_manager.create_cognito_only_user(user_id, 'real')


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
    view_manager.record_views_for_comments = Mock()
    view_manager.record_views_for_chat_messages = Mock()
    view_manager.record_views_for_posts = Mock()

    # call with no ids
    viewed_at = pendulum.now('utc')
    view_manager.record_views('chat_message', [], 'vuid', viewed_at)
    assert view_manager.record_views_for_comments.mock_calls == []
    assert view_manager.record_views_for_chat_messages.mock_calls == []
    assert view_manager.record_views_for_posts.mock_calls == []

    # do some meaningfull calls
    view_manager.record_views('chat_message', ['chid2', 'chid2'], 'vuid', viewed_at)
    view_manager.record_views('comment', ['cid1'], 'vuid', viewed_at)
    view_manager.record_views('post', ['pid1', 'pid2', 'pid1'], 'vuid', viewed_at)
    assert view_manager.record_views_for_chat_messages.mock_calls == [
        call({'chid2': 2}, 'vuid', viewed_at),
    ]
    assert view_manager.record_views_for_comments.mock_calls == [
        call({'cid1': 1}, 'vuid', viewed_at),
    ]
    assert view_manager.record_views_for_posts.mock_calls == [
        call({'pid1': 2, 'pid2': 1}, 'vuid', viewed_at),
    ]


def test_cant_record_view_bad_item_type(view_manager):
    with pytest.raises(AssertionError, match='Unknown item type'):
        view_manager.record_views('DNE-item-type', ['an-id'], None)


def test_record_views_for_chat_messages(view_manager, chat_message, user2, caplog):
    grouped_message_ids = {'cmid-dne': 1, chat_message.id: 2}
    now = pendulum.now('utc')
    view_manager.record_view_for_chat_message = Mock()

    with caplog.at_level(logging.WARNING):
        # logs warning for chat_message that DNE
        view_manager.record_views_for_chat_messages(grouped_message_ids, user2.id, now)

    # check logging
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == 'WARNING'
    assert f'`{user2.id}`' in caplog.records[0].msg
    assert f'`cmid-dne`' in caplog.records[0].msg
    assert 'DNE' in caplog.records[0].msg

    # check calls to Mock
    assert len(view_manager.record_view_for_chat_message.call_args_list) == 1
    assert view_manager.record_view_for_chat_message.call_args_list[0].kwargs == {}
    assert view_manager.record_view_for_chat_message.call_args_list[0].args[0].id == chat_message.id
    assert view_manager.record_view_for_chat_message.call_args_list[0].args[1] == user2.id
    assert view_manager.record_view_for_chat_message.call_args_list[0].args[2] == 2
    assert view_manager.record_view_for_chat_message.call_args_list[0].args[3] == now


def test_record_view_chat_message(view_manager, chat_message, user2):
    # check there is no view
    assert view_manager.get_viewed_status(chat_message, user2.id) == 'NOT_VIEWED'

    # add a view, check that it worked
    resp = view_manager.record_view_for_chat_message(chat_message, user2.id, 2, pendulum.now('utc'))
    assert resp is True
    assert view_manager.get_viewed_status(chat_message, user2.id) == 'VIEWED'


def test_record_view_comment(view_manager, comment, user2):
    # check there is no view
    assert view_manager.get_viewed_status(comment, user2.id) == 'NOT_VIEWED'

    # add a view, check that it worked
    resp = view_manager.record_view_for_comment(comment, user2.id, 2, pendulum.now('utc'))
    assert resp is True
    assert view_manager.get_viewed_status(comment, user2.id) == 'VIEWED'


def test_record_views_comments_clears_new_comment_activity(view_manager, comment_manager, posts, user, user2, user3):
    post, _ = posts

    # add a comment by a different user to get some activity on the post
    comment = comment_manager.add_comment('cmid2', post.id, user2.id, 'witty comment')
    post.refresh_item()
    assert post.item.get('hasNewCommentActivity', False) is True
    user.refresh_item()
    assert user.item.get('postHasNewCommentActivityCount', 0) == 1

    # record a view of that comment by a user that is not the post owner
    view_manager.record_views_for_comments({comment.id: 2}, user3.id, pendulum.now('utc'))

    # verify the post still has comment activity
    post.refresh_item()
    assert post.item.get('hasNewCommentActivity', False) is True
    user.refresh_item()
    assert user.item.get('postHasNewCommentActivityCount', 0) == 1

    # record a view of that comment by the post owner
    view_manager.record_views_for_comments({comment.id: 2}, user.id, pendulum.now('utc'))

    # verify the post now has no comment activity
    post.refresh_item()
    assert post.item.get('hasNewCommentActivity', False) is False
    user.refresh_item()
    assert user.item.get('postHasNewCommentActivityCount', 0) == 0


def test_record_views_for_comments(view_manager, comment_manager, posts, user, user2, caplog):
    post, _ = posts

    # two comments by a different user
    comment1 = comment_manager.add_comment('cmid2', post.id, user2.id, 'witty comment')
    comment2 = comment_manager.add_comment('cmid3', post.id, user2.id, 'witty comment')

    # Mock methods we want to verify called correctly
    view_manager.record_view_for_comment = Mock()
    view_manager.post_manager.get_post = Mock(return_value=post)
    post.set_new_comment_activity = Mock()

    # post owner views both comments, including one that doesn't exist
    now = pendulum.now('utc')
    grouped_comment_ids = {'cid-dne': 1, comment1.id: 2, comment2.id: 1}
    with caplog.at_level(logging.WARNING):
        view_manager.record_views_for_comments(grouped_comment_ids, user.id, now)

    # check logging
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == 'WARNING'
    assert f'`{user.id}`' in caplog.records[0].msg
    assert f'`cid-dne`' in caplog.records[0].msg
    assert 'DNE' in caplog.records[0].msg

    # check calls to Mock
    assert len(view_manager.record_view_for_comment.call_args_list) == 2
    assert view_manager.record_view_for_comment.call_args_list[0].kwargs == {}
    assert view_manager.record_view_for_comment.call_args_list[1].kwargs == {}
    assert view_manager.record_view_for_comment.call_args_list[0].args[0].id == comment1.id
    assert view_manager.record_view_for_comment.call_args_list[1].args[0].id == comment2.id
    assert view_manager.record_view_for_comment.call_args_list[0].args[1] == user.id
    assert view_manager.record_view_for_comment.call_args_list[1].args[1] == user.id
    assert view_manager.record_view_for_comment.call_args_list[0].args[2] == 2
    assert view_manager.record_view_for_comment.call_args_list[1].args[2] == 1
    assert view_manager.record_view_for_comment.call_args_list[0].args[3] == now
    assert view_manager.record_view_for_comment.call_args_list[1].args[3] == now

    # verify post set comment activity called only once
    assert view_manager.post_manager.get_post.mock_calls == [call(post.id)]
    assert post.set_new_comment_activity.mock_calls == [call(False)]


def test_record_views_for_posts(view_manager, posts, caplog):
    user_id = 'vuid'
    post_ids = {'pid-dne': 1, posts[0].id: 1, posts[1].id: 2}
    now = pendulum.now('utc')
    view_manager.record_view_for_post = Mock()

    with caplog.at_level(logging.WARNING):
        # logs warning for post that DNE
        view_manager.record_views_for_posts(post_ids, user_id, now)

    # check logging
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == 'WARNING'
    assert f'`{user_id}`' in caplog.records[0].msg
    assert f'`pid-dne`' in caplog.records[0].msg
    assert 'DNE' in caplog.records[0].msg

    # check calls to Mock
    assert len(view_manager.record_view_for_post.call_args_list) == 2
    assert view_manager.record_view_for_post.call_args_list[0].kwargs == {}
    assert view_manager.record_view_for_post.call_args_list[1].kwargs == {}
    assert view_manager.record_view_for_post.call_args_list[0].args[0].id == posts[0].id
    assert view_manager.record_view_for_post.call_args_list[1].args[0].id == posts[1].id
    assert view_manager.record_view_for_post.call_args_list[0].args[1] == user_id
    assert view_manager.record_view_for_post.call_args_list[1].args[1] == user_id
    assert view_manager.record_view_for_post.call_args_list[0].args[2] == 1
    assert view_manager.record_view_for_post.call_args_list[1].args[2] == 2
    assert view_manager.record_view_for_post.call_args_list[0].args[3] == now
    assert view_manager.record_view_for_post.call_args_list[1].args[3] == now


def test_record_view_post_not_completed(view_manager, posts, caplog, post_manager, user_manager, trending_manager):
    user_id = 'vuid'

    # set up an archived post
    post = posts[0]
    post.archive()

    # try to record a view on it
    with caplog.at_level(logging.WARNING):
        # fails with logged warning
        resp = view_manager.record_view_for_post(post, user_id, 3, pendulum.now('utc'))
        assert resp is False

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
    resp = view_manager.record_view_for_post(post, viewed_by_user_id, 2, pendulum.now('utc'))
    assert resp is True
    assert view_manager.get_viewed_status(post, viewed_by_user_id) == 'VIEWED'

    # check the viewedByCounts and the trending indexes all incremented
    assert post_manager.dynamo.get_post(post.id).get('viewedByCount', 0) == 1
    assert user_manager.dynamo.get_user(post.user_id).get('postViewedByCount', 0) == 1
    assert trending_manager.dynamo.get_trending(post.id).get('gsiK3SortKey', 0) == 1
    assert trending_manager.dynamo.get_trending(post.user_id).get('gsiK3SortKey', 0) == 1

    # record a second post view for this user on this post
    resp = view_manager.record_view_for_post(post, viewed_by_user_id, 1, pendulum.now('utc'))
    assert resp is True
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
    resp = view_manager.record_view_for_post(post, post.user_id, 1, pendulum.now('utc'))
    assert resp is False
    assert view_manager.get_viewed_status(post, post.user_id) == 'VIEWED'
    assert view_manager.dynamo.get_view(post.item['partitionKey'], post.user_id) is None

    # check the view was not recorded in the DB
    assert post_manager.dynamo.get_post(post.id).get('viewedByCount', 0) == 0
    assert user_manager.dynamo.get_user(post.user_id).get('postViewedByCount', 0) == 0

    # but it was recorded for the trending indexes
    assert trending_manager.dynamo.get_trending(post.id).get('gsiK3SortKey', 0) == 1
    assert trending_manager.dynamo.get_trending(post.user_id).get('gsiK3SortKey', 0) == 1


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
    resp = view_manager.record_view_for_post(non_org_post, viewed_by_user_id, view_count, viewed_at)
    assert resp is True

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
    resp = view_manager.record_view_for_post(org_post, viewed_by_user_id, new_view_count, new_viewed_at)
    assert resp is True

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


def test_record_view_day_old_post_doesnt_trend(view_manager, post_manager, user_manager, trending_manager, user):
    viewed_by_user_id = 'vuid'
    now = pendulum.now('utc')

    # add a post over a day ago
    posted_at = now - pendulum.duration(days=2)
    post = post_manager.add_post(user.id, 'pid2', PostType.TEXT_ONLY, text='t', now=posted_at)

    # check there is no post view yet recorded for this user on this post
    assert view_manager.get_viewed_status(post, viewed_by_user_id) == 'NOT_VIEWED'
    assert post_manager.dynamo.get_post(post.id).get('viewedByCount', 0) == 0
    assert user_manager.dynamo.get_user(post.user_id).get('postViewedByCount', 0) == 0
    assert trending_manager.dynamo.get_trending(post.id) is None
    assert trending_manager.dynamo.get_trending(post.user_id) is None

    # record the first post view
    resp = view_manager.record_view_for_post(post, viewed_by_user_id, 2, pendulum.now('utc'))
    assert resp is True
    assert view_manager.get_viewed_status(post, viewed_by_user_id) == 'VIEWED'

    # check the viewedByCounts incremented but the trending indexes did not
    assert post_manager.dynamo.get_post(post.id).get('viewedByCount', 0) == 1
    assert user_manager.dynamo.get_user(post.user_id).get('postViewedByCount', 0) == 1
    assert trending_manager.dynamo.get_trending(post.id) is None
    assert trending_manager.dynamo.get_trending(post.user_id) is None


def test_record_view_real_user_doesnt_trend(view_manager, post_manager, user_manager, trending_manager, real_user):
    viewed_by_user_id = 'vuid'

    # real user adds a post
    post = post_manager.add_post(real_user.id, 'pid2', PostType.TEXT_ONLY, text='t')

    # check there is no post view yet recorded for this user on this post
    assert view_manager.get_viewed_status(post, viewed_by_user_id) == 'NOT_VIEWED'
    assert post_manager.dynamo.get_post(post.id).get('viewedByCount', 0) == 0
    assert user_manager.dynamo.get_user(post.user_id).get('postViewedByCount', 0) == 0
    assert trending_manager.dynamo.get_trending(post.id) is None
    assert trending_manager.dynamo.get_trending(post.user_id) is None

    # record the first post view
    resp = view_manager.record_view_for_post(post, viewed_by_user_id, 2, pendulum.now('utc'))
    assert resp is True
    assert view_manager.get_viewed_status(post, viewed_by_user_id) == 'VIEWED'

    # check the viewedByCounts incremented but the trending indexes did not
    assert post_manager.dynamo.get_post(post.id).get('viewedByCount', 0) == 1
    assert user_manager.dynamo.get_user(post.user_id).get('postViewedByCount', 0) == 1
    assert trending_manager.dynamo.get_trending(post.id) is None
    assert trending_manager.dynamo.get_trending(post.user_id) is None


def test_record_view_post_failed_verif_doesnt_trend(view_manager, post_manager, trending_manager, image_data_b64,
                                                    user, grant_data_b64):
    viewed_by_user_id = 'vuid'

    # real user adds two identical image posts, mark one as failed verificaiton
    post1 = post_manager.add_post(user.id, 'pid1', PostType.IMAGE, image_input={'imageData': image_data_b64})
    post2 = post_manager.add_post(user.id, 'pid2', PostType.IMAGE, image_input={'imageData': grant_data_b64})
    post2.dynamo.set_is_verified(post2.id, False)
    post2.refresh_item()

    # check there is no trending for either post or the user
    assert trending_manager.dynamo.get_trending(post1.id) is None
    assert trending_manager.dynamo.get_trending(post2.id) is None
    assert trending_manager.dynamo.get_trending(user.id) is None

    # record a view on each post
    resp = view_manager.record_view_for_post(post1, viewed_by_user_id, 1, pendulum.now('utc'))
    assert resp is True
    resp = view_manager.record_view_for_post(post2, viewed_by_user_id, 1, pendulum.now('utc'))
    assert resp is True

    # check the verified post is trending but the non-verified isn't
    assert trending_manager.dynamo.get_trending(post1.id).get('gsiK3SortKey', 0) == 1
    assert trending_manager.dynamo.get_trending(post2.id) is None
    assert trending_manager.dynamo.get_trending(user.id).get('gsiK3SortKey', 0) == 1


def test_write_view_to_dynamo(view_manager):
    partition_key = 'partKey'
    user_id = 'uid'

    # check starting state
    assert view_manager.dynamo.get_view(partition_key, user_id) is None

    # record a view for the first time, check it was recorded
    view_manager.write_view_to_dynamo(partition_key, user_id, 1, pendulum.now('utc'))
    assert view_manager.dynamo.get_view(partition_key, user_id)['viewCount'] == 1

    # record some more views, check they were recorded
    view_manager.write_view_to_dynamo(partition_key, user_id, 2, pendulum.now('utc'))
    assert view_manager.dynamo.get_view(partition_key, user_id)['viewCount'] == 3
