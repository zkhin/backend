import pendulum
import pytest


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
    assert 'lastMessageActivityAt' not in chat.item

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
    assert chat.item['lastMessageActivityAt'] == now.to_iso8601_string()


def test_truncate_chat_messages(chat_message_manager, user, chat, view_manager):
    # add two messsages
    message_id_1, message_id_2 = 'mid1', 'mid2'

    message_1 = chat_message_manager.add_chat_message(message_id_1, 'lore', chat.id, user.id)
    assert message_1.id == message_id_1

    message_2 = chat_message_manager.add_chat_message(message_id_2, 'ipsum', chat.id, user.id)
    assert message_2.id == message_id_2

    # add some views to the messsages, verify we see them in the db
    view_manager.record_views('chat_message', ['mid1', 'mid2', 'mid1'], 'uid')
    assert view_manager.dynamo.get_view('chatMessage/mid1', 'uid')
    assert view_manager.dynamo.get_view('chatMessage/mid2', 'uid')

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

    # check the message views have also been deleted
    assert view_manager.dynamo.get_view('chatMessage/mid1', 'uid') is None
    assert view_manager.dynamo.get_view('chatMessage/mid2', 'uid') is None
