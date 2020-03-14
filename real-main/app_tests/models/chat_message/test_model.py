import pytest

from app.models.chat_message.enums import ViewedStatus


@pytest.fixture
def user1(user_manager):
    yield user_manager.create_cognito_only_user('pbuid', 'pbUname')


@pytest.fixture
def user2(user_manager):
    yield user_manager.create_cognito_only_user('pbuid2', 'pbUname2')


@pytest.fixture
def chat(chat_manager, user1, user2):
    yield chat_manager.add_direct_chat('cid', user1.id, user2.id)


def test_chat_message_serialize(chat_message_manager, user1, user2, chat):
    # user1 adds a message
    message_id = 'mid'
    text = 'lore ipsum'
    message = chat_message_manager.add_chat_message(message_id, text, chat.id, user1.id)
    assert message.id == message_id

    # check that user1 has viewed it (since they wrote it) and user2 has not
    message.serialize(user1.id)['viewedStatus'] == ViewedStatus.VIEWED
    message.serialize(user2.id)['viewedStatus'] == ViewedStatus.NOT_VIEWED

    # user2 reports to ahve viewed it, check that reflects in the viewedStatus
    chat_message_manager.record_views(user2.id, [message_id])
    message.serialize(user2.id)['viewedStatus'] == ViewedStatus.VIEWED
