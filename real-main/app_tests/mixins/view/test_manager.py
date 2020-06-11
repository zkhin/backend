import pytest


@pytest.mark.parametrize(
    'manager', pytest.lazy_fixture(['post_manager', 'comment_manager', 'chat_message_manager']),
)
def test_record_views_implemented(manager):
    # should not error out
    manager.record_views(['iid1', 'iid2'], 'uid')
