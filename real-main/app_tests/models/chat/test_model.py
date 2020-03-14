import pytest


@pytest.fixture
def user1(user_manager):
    yield user_manager.create_cognito_only_user('pbuid', 'pbUname')


@pytest.fixture
def user2(user_manager):
    yield user_manager.create_cognito_only_user('pbuid2', 'pbUname2')


@pytest.fixture
def direct_chat(chat_manager, user1, user2):
    yield chat_manager.add_direct_chat('cid', user1.id, user2.id)


def test_leave_direct_chat(direct_chat, user1, user2):
    # verify user totals are as expected
    user1.refresh_item()
    user2.refresh_item()
    assert user1.item['chatCount'] == 1
    assert user2.item['chatCount'] == 1

    # verify we see the chat and chat_memberships in the DB
    assert direct_chat.dynamo.get_chat(direct_chat.id)
    assert direct_chat.dynamo.get_chat_membership(direct_chat.id, user1.id)
    assert direct_chat.dynamo.get_chat_membership(direct_chat.id, user2.id)

    # leaving the direct chat should trigger its deletion
    direct_chat.leave_chat(user2.id)

    # verify user totals are as expected
    user1.refresh_item()
    user2.refresh_item()
    assert user1.item['chatCount'] == 0
    assert user2.item['chatCount'] == 0

    # verify we see the chat and chat_memberships have disapeared from DB
    assert direct_chat.dynamo.get_chat(direct_chat.id) is None
    assert direct_chat.dynamo.get_chat_membership(direct_chat.id, user1.id) is None
    assert direct_chat.dynamo.get_chat_membership(direct_chat.id, user2.id) is None


def test_delete_direct_chat(direct_chat, user1, user2):
    # verify user totals are as expected
    user1.refresh_item()
    user2.refresh_item()
    assert user1.item['chatCount'] == 1
    assert user2.item['chatCount'] == 1

    # verify we see the chat and chat_memberships in the DB
    assert direct_chat.dynamo.get_chat(direct_chat.id)
    assert direct_chat.dynamo.get_chat_membership(direct_chat.id, user1.id)
    assert direct_chat.dynamo.get_chat_membership(direct_chat.id, user2.id)

    # delete the chat
    direct_chat.delete_direct_chat()

    # verify user totals are as expected
    user1.refresh_item()
    user2.refresh_item()
    assert user1.item['chatCount'] == 0
    assert user2.item['chatCount'] == 0

    # verify we see the chat and chat_memberships have disapeared from DB
    assert direct_chat.dynamo.get_chat(direct_chat.id) is None
    assert direct_chat.dynamo.get_chat_membership(direct_chat.id, user1.id) is None
    assert direct_chat.dynamo.get_chat_membership(direct_chat.id, user2.id) is None


def test_delete_direct_chat_non_direct_chat(direct_chat):
    # TODO: would be better to just use a group chat, change to that once they're implemented
    chat = direct_chat
    chat.type = chat.item['chatType'] = 'anything-but-direct'
    with pytest.raises(AssertionError, match='non-DIRECT chats'):
        chat.delete_direct_chat()


def test_delete_direct_chat_non_participant(direct_chat):
    # in mem change is enough
    with pytest.raises(Exception, match='not authorized to delete'):
        direct_chat.delete_direct_chat(leaving_user_id='not-in-chat-uid')
