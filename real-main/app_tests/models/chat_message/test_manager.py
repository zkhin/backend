import pendulum
import pytest

from app.models.chat_message.enums import ViewedStatus


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
def chat(chat_manager, user2, user3):
    yield chat_manager.add_direct_chat('cid', user2.id, user3.id)


def test_add_chat_message(chat_message_manager, user, chat):
    now = pendulum.now('utc')
    username = user.item['username']
    text = f'whats up with @{username}?'
    message_id = 'mid'
    user_id = 'uid'

    # check message count starts off at zero
    assert 'messageCount' not in chat.item
    assert 'lastMessageAt' not in chat.item

    # add the message, check it looks ok
    message = chat_message_manager.add_chat_message(message_id, text, chat.id, user_id, now=now)
    assert message.id == message_id
    assert message.user_id == user_id
    assert message.item['createdAt'] == now.to_iso8601_string()
    assert message.item['text'] == text
    assert message.item['textTags'] == [{'tag': f'@{username}', 'userId': user.id}]

    # check the chat was altered correctly
    chat.refresh_item()
    assert chat.item['messageCount'] == 1
    assert chat.item['lastMessageAt'] == now.to_iso8601_string()


def test_record_views(chat_message_manager, user, chat, user2):
    # add two messsages
    message_id_1, message_id_2 = 'mid1', 'mid2'

    message_1 = chat_message_manager.add_chat_message(message_id_1, 'lore', chat.id, user.id)
    assert message_1.id == message_id_1

    message_2 = chat_message_manager.add_chat_message(message_id_2, 'ipsum', chat.id, user.id)
    assert message_2.id == message_id_2

    # check user2 has not viewed either
    message_1.serialize(user2.id)['viewedStatus'] == ViewedStatus.NOT_VIEWED
    message_2.serialize(user2.id)['viewedStatus'] == ViewedStatus.NOT_VIEWED

    # user2 reprots to have viewed both messages
    chat_message_manager.record_views(user2.id, [message_id_1, message_id_2])

    # check user2 has now viewed both
    message_1.refresh_item()
    message_2.refresh_item()
    message_1.serialize(user2.id)['viewedStatus'] == ViewedStatus.VIEWED
    message_2.serialize(user2.id)['viewedStatus'] == ViewedStatus.VIEWED


def test_truncate_chat_messages(chat_message_manager, user, chat):
    # add two messsages
    message_id_1, message_id_2 = 'mid1', 'mid2'

    message_1 = chat_message_manager.add_chat_message(message_id_1, 'lore', chat.id, user.id)
    assert message_1.id == message_id_1

    message_2 = chat_message_manager.add_chat_message(message_id_2, 'ipsum', chat.id, user.id)
    assert message_2.id == message_id_2

    # check the chat total is correct
    chat.refresh_item()
    assert chat.item['messageCount'] == 2

    # truncate the messages
    chat_message_manager.truncate_chat_messages(chat.id)

    # check the chat itself was not deleted, including the message total
    chat.refresh_item()
    assert chat.item['messageCount'] == 2

    # check the two messages have been deleted
    assert chat_message_manager.get_chat_message(message_id_1) is None
    assert chat_message_manager.get_chat_message(message_id_2) is None
