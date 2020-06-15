/* eslint-env jest */

const moment = require('moment')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const {mutations, queries} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Add messages to a direct chat', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // they open up a chat with us
  const [chatId, messageId1, text1] = [uuidv4(), uuidv4(), 'hey this is msg 1']
  let variables = {userId: ourUserId, chatId, messageId: messageId1, messageText: text1}
  let resp = await theirClient.mutate({mutation: mutations.createDirectChat, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.createDirectChat.chatId).toBe(chatId)
  expect(resp.data.createDirectChat.messages.items).toHaveLength(1)
  expect(resp.data.createDirectChat.messages.items[0].messageId).toBe(messageId1)
  expect(resp.data.createDirectChat.messages.items[0].text).toBe(text1)

  // we add two messages to the chat
  const [messageId2, text2] = [uuidv4(), 'msg 2']
  variables = {chatId, messageId: messageId2, text: text2}
  resp = await ourClient.mutate({mutation: mutations.addChatMessage, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addChatMessage.messageId).toBe(messageId2)
  expect(resp.data.addChatMessage.text).toBe(text2)
  expect(resp.data.addChatMessage.chat.chatId).toBe(chatId)

  const [messageId3, text3] = [uuidv4(), 'msg 3']
  variables = {chatId, messageId: messageId3, text: text3}
  resp = await ourClient.mutate({mutation: mutations.addChatMessage, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addChatMessage.messageId).toBe(messageId3)
  expect(resp.data.addChatMessage.text).toBe(text3)
  expect(resp.data.addChatMessage.chat.chatId).toBe(chatId)

  // they add another message to the chat, check the timestamp
  const [messageId4, text4] = [uuidv4(), 'msg 4']
  variables = {chatId, messageId: messageId4, text: text4}
  let before = moment().toISOString()
  resp = await theirClient.mutate({mutation: mutations.addChatMessage, variables})
  let after = moment().toISOString()
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addChatMessage.messageId).toBe(messageId4)
  expect(resp.data.addChatMessage.text).toBe(text4)
  expect(resp.data.addChatMessage.chat.chatId).toBe(chatId)
  const lastMessageCreatedAt = resp.data.addChatMessage.createdAt
  expect(before <= lastMessageCreatedAt).toBe(true)
  expect(after >= lastMessageCreatedAt).toBe(true)

  // check we see all the messages are there in the expected order
  resp = await ourClient.query({query: queries.chat, variables: {chatId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.chat.chatId).toBe(chatId)
  expect(resp.data.chat.lastMessageActivityAt).toBe(lastMessageCreatedAt)
  expect(resp.data.chat.messageCount).toBe(4)
  expect(resp.data.chat.messages.items).toHaveLength(4)
  expect(resp.data.chat.messages.items[0].messageId).toBe(messageId1)
  expect(resp.data.chat.messages.items[1].messageId).toBe(messageId2)
  expect(resp.data.chat.messages.items[2].messageId).toBe(messageId3)
  expect(resp.data.chat.messages.items[3].messageId).toBe(messageId4)
  expect(resp.data.chat.messages.items[0].text).toBe(text1)
  expect(resp.data.chat.messages.items[1].text).toBe(text2)
  expect(resp.data.chat.messages.items[2].text).toBe(text3)
  expect(resp.data.chat.messages.items[3].text).toBe(text4)
  expect(resp.data.chat.messages.items[0].author.userId).toBe(theirUserId)
  expect(resp.data.chat.messages.items[0].authorUserId).toBe(theirUserId)
  expect(resp.data.chat.messages.items[1].author.userId).toBe(ourUserId)
  expect(resp.data.chat.messages.items[1].authorUserId).toBe(ourUserId)
  expect(resp.data.chat.messages.items[2].author.userId).toBe(ourUserId)
  expect(resp.data.chat.messages.items[2].authorUserId).toBe(ourUserId)
  expect(resp.data.chat.messages.items[3].author.userId).toBe(theirUserId)
  expect(resp.data.chat.messages.items[3].authorUserId).toBe(theirUserId)
  expect(resp.data.chat.messages.items[0].viewedStatus).toBe('NOT_VIEWED')
  expect(resp.data.chat.messages.items[1].viewedStatus).toBe('VIEWED')
  expect(resp.data.chat.messages.items[2].viewedStatus).toBe('VIEWED')
  expect(resp.data.chat.messages.items[3].viewedStatus).toBe('NOT_VIEWED')

  // check they can also see them, and in reverse order if they want
  resp = await theirClient.query({query: queries.chat, variables: {chatId, reverse: true}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.chat.chatId).toBe(chatId)
  expect(resp.data.chat.lastMessageActivityAt).toBe(lastMessageCreatedAt)
  expect(resp.data.chat.messageCount).toBe(4)
  expect(resp.data.chat.messages.items).toHaveLength(4)
  expect(resp.data.chat.messages.items[0].messageId).toBe(messageId4)
  expect(resp.data.chat.messages.items[1].messageId).toBe(messageId3)
  expect(resp.data.chat.messages.items[2].messageId).toBe(messageId2)
  expect(resp.data.chat.messages.items[3].messageId).toBe(messageId1)
  expect(resp.data.chat.messages.items[0].viewedStatus).toBe('VIEWED')
  expect(resp.data.chat.messages.items[1].viewedStatus).toBe('NOT_VIEWED')
  expect(resp.data.chat.messages.items[2].viewedStatus).toBe('NOT_VIEWED')
  expect(resp.data.chat.messages.items[3].viewedStatus).toBe('VIEWED')
})

test('Report message views', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()
  const [chatId, messageId1, messageId2, messageId3] = [uuidv4(), uuidv4(), uuidv4(), uuidv4()]

  // they open up a chat with us
  let variables = {userId: ourUserId, chatId, messageId: messageId1, messageText: 'lore'}
  let resp = await theirClient.mutate({mutation: mutations.createDirectChat, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.createDirectChat.chatId).toBe(chatId)
  expect(resp.data.createDirectChat.messages.items).toHaveLength(1)
  expect(resp.data.createDirectChat.messages.items[0].messageId).toBe(messageId1)
  expect(resp.data.createDirectChat.messages.items[0].viewedStatus).toBe('VIEWED')

  // we add two messages to the chat
  variables = {chatId, messageId: messageId2, text: 'lore'}
  resp = await ourClient.mutate({mutation: mutations.addChatMessage, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addChatMessage.messageId).toBe(messageId2)
  expect(resp.data.addChatMessage.viewedStatus).toBe('VIEWED')

  variables = {chatId, messageId: messageId3, text: 'lore'}
  resp = await ourClient.mutate({mutation: mutations.addChatMessage, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addChatMessage.messageId).toBe(messageId3)
  expect(resp.data.addChatMessage.viewedStatus).toBe('VIEWED')

  // check each message's viewedStatus is as expected for both of us
  resp = await ourClient.query({query: queries.chat, variables: {chatId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.chat.chatId).toBe(chatId)
  expect(resp.data.chat.messageCount).toBe(3)
  expect(resp.data.chat.messages.items).toHaveLength(3)
  expect(resp.data.chat.messages.items[0].messageId).toBe(messageId1)
  expect(resp.data.chat.messages.items[1].messageId).toBe(messageId2)
  expect(resp.data.chat.messages.items[2].messageId).toBe(messageId3)
  expect(resp.data.chat.messages.items[0].viewedStatus).toBe('NOT_VIEWED')
  expect(resp.data.chat.messages.items[1].viewedStatus).toBe('VIEWED')
  expect(resp.data.chat.messages.items[2].viewedStatus).toBe('VIEWED')

  resp = await theirClient.query({query: queries.chat, variables: {chatId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.chat.chatId).toBe(chatId)
  expect(resp.data.chat.messageCount).toBe(3)
  expect(resp.data.chat.messages.items).toHaveLength(3)
  expect(resp.data.chat.messages.items[0].messageId).toBe(messageId1)
  expect(resp.data.chat.messages.items[1].messageId).toBe(messageId2)
  expect(resp.data.chat.messages.items[2].messageId).toBe(messageId3)
  expect(resp.data.chat.messages.items[0].viewedStatus).toBe('VIEWED')
  expect(resp.data.chat.messages.items[1].viewedStatus).toBe('NOT_VIEWED')
  expect(resp.data.chat.messages.items[2].viewedStatus).toBe('NOT_VIEWED')

  // we report to have viewed the first message (and one we've already viewed, which should be a no-op)
  variables = {messageIds: [messageId1, messageId2]}
  resp = await ourClient.mutate({mutation: mutations.reportChatMessageViews, variables})
  expect(resp.errors).toBeUndefined()

  // check we have now viewed all messages
  resp = await ourClient.query({query: queries.chat, variables: {chatId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.chat.chatId).toBe(chatId)
  expect(resp.data.chat.messageCount).toBe(3)
  expect(resp.data.chat.messages.items).toHaveLength(3)
  expect(resp.data.chat.messages.items[0].messageId).toBe(messageId1)
  expect(resp.data.chat.messages.items[1].messageId).toBe(messageId2)
  expect(resp.data.chat.messages.items[2].messageId).toBe(messageId3)
  expect(resp.data.chat.messages.items[0].viewedStatus).toBe('VIEWED')
  expect(resp.data.chat.messages.items[1].viewedStatus).toBe('VIEWED')
  expect(resp.data.chat.messages.items[2].viewedStatus).toBe('VIEWED')

  // they report they have viewed the two message they haven't viewed
  variables = {messageIds: [messageId2, messageId3]}
  resp = await theirClient.mutate({mutation: mutations.reportChatMessageViews, variables})
  expect(resp.errors).toBeUndefined()

  // check they have now viewed all messages
  resp = await theirClient.query({query: queries.chat, variables: {chatId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.chat.chatId).toBe(chatId)
  expect(resp.data.chat.messageCount).toBe(3)
  expect(resp.data.chat.messages.items).toHaveLength(3)
  expect(resp.data.chat.messages.items[0].messageId).toBe(messageId1)
  expect(resp.data.chat.messages.items[1].messageId).toBe(messageId2)
  expect(resp.data.chat.messages.items[2].messageId).toBe(messageId3)
  expect(resp.data.chat.messages.items[0].viewedStatus).toBe('VIEWED')
  expect(resp.data.chat.messages.items[1].viewedStatus).toBe('VIEWED')
  expect(resp.data.chat.messages.items[2].viewedStatus).toBe('VIEWED')
})

test('Disabled user cannot add, edit, delete or report views of chat messages', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // we create a group chat with just us in it
  const chatId = uuidv4()
  const messageId = uuidv4()
  let variables = {chatId, userIds: [], messageId, messageText: 'm1'}
  let resp = await ourClient.mutate({mutation: mutations.createGroupChat, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.createGroupChat.chatId).toBe(chatId)

  // we disable ourselves
  resp = await ourClient.mutate({mutation: mutations.disableUser})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.disableUser.userId).toBe(ourUserId)
  expect(resp.data.disableUser.userStatus).toBe('DISABLED')

  // verify we cannot add a message to that chat
  variables = {chatId, messageId: uuidv4(), text: 'lore'}
  await expect(ourClient.mutate({mutation: mutations.addChatMessage, variables})).rejects.toThrow(
    /ClientError: User .* is not ACTIVE/,
  )

  // verify we cannot edit our chat message
  await expect(
    ourClient.mutate({mutation: mutations.editChatMessage, variables: {messageId, text: 'lore new'}}),
  ).rejects.toThrow(/ClientError: User .* is not ACTIVE/)

  // verify we cannot edit our chat message
  await expect(ourClient.mutate({mutation: mutations.deleteChatMessage, variables: {messageId}})).rejects.toThrow(
    /ClientError: User .* is not ACTIVE/,
  )

  await expect(
    ourClient.mutate({mutation: mutations.reportChatMessageViews, variables: {messageIds: [messageId]}}),
  ).rejects.toThrow(/ClientError: User .* is not ACTIVE/)
})

test('Cant add a message to a chat we are not in', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()
  const [randoClient] = await loginCache.getCleanLogin()
  const [chatId, messageId] = [uuidv4(), uuidv4()]

  // they open up a chat with us
  let variables = {userId: ourUserId, chatId, messageId, messageText: 'lore'}
  let resp = await theirClient.mutate({mutation: mutations.createDirectChat, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.createDirectChat.chatId).toBe(chatId)

  // verify the rando can't add a message to our chat
  variables = {chatId, messageId: uuidv4(), text: 'lore'}
  await expect(randoClient.mutate({mutation: mutations.addChatMessage, variables})).rejects.toThrow(
    /ClientError: .* is not a member/,
  )

  // check the chat and verify the rando's message didn't get saved
  resp = await ourClient.query({query: queries.chat, variables: {chatId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.chat.chatId).toBe(chatId)
  expect(resp.data.chat.messageCount).toBe(1)
  expect(resp.data.chat.messages.items).toHaveLength(1)
  expect(resp.data.chat.messages.items[0].messageId).toBe(messageId)
})

test('Tag users in a chat message', async () => {
  const [ourClient, ourUserId, , , ourUsername] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId, , , theirUsername] = await loginCache.getCleanLogin()
  const [chatId, messageId1, messageId2, messageId3] = [uuidv4(), uuidv4(), uuidv4(), uuidv4()]

  // they open up a chat with us, with a tags in the message
  let text = `hi @${theirUsername}! hi from @${ourUsername}`
  let variables = {userId: ourUserId, chatId, messageId: messageId1, messageText: text}
  let resp = await theirClient.mutate({mutation: mutations.createDirectChat, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.createDirectChat.chatId).toBe(chatId)
  expect(resp.data.createDirectChat.messages.items).toHaveLength(1)
  expect(resp.data.createDirectChat.messages.items[0].messageId).toBe(messageId1)
  expect(resp.data.createDirectChat.messages.items[0].text).toBe(text)
  expect(resp.data.createDirectChat.messages.items[0].textTaggedUsers).toHaveLength(2)

  // we add a message with one tag
  text = `hi @${theirUsername}!`
  variables = {chatId, messageId: messageId2, text}
  resp = await ourClient.mutate({mutation: mutations.addChatMessage, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addChatMessage.messageId).toBe(messageId2)
  expect(resp.data.addChatMessage.text).toBe(text)
  expect(resp.data.addChatMessage.textTaggedUsers).toHaveLength(1)
  expect(resp.data.addChatMessage.textTaggedUsers[0].tag).toBe(`@${theirUsername}`)
  expect(resp.data.addChatMessage.textTaggedUsers[0].user.userId).toBe(theirUserId)

  // we add a message with no tags
  text = 'not tagging anyone here'
  variables = {chatId, messageId: messageId3, text}
  resp = await ourClient.mutate({mutation: mutations.addChatMessage, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addChatMessage.messageId).toBe(messageId3)
  expect(resp.data.addChatMessage.text).toBe(text)
  expect(resp.data.addChatMessage.textTaggedUsers).toHaveLength(0)

  // check the chat, make sure the tags all look as expected
  resp = await theirClient.query({query: queries.chat, variables: {chatId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.chat.chatId).toBe(chatId)
  expect(resp.data.chat.messageCount).toBe(3)
  expect(resp.data.chat.messages.items).toHaveLength(3)
  expect(resp.data.chat.messages.items[0].messageId).toBe(messageId1)
  expect(resp.data.chat.messages.items[1].messageId).toBe(messageId2)
  expect(resp.data.chat.messages.items[2].messageId).toBe(messageId3)
  expect(resp.data.chat.messages.items[0].textTaggedUsers).toHaveLength(2)
  expect(resp.data.chat.messages.items[1].textTaggedUsers).toHaveLength(1)
  expect(resp.data.chat.messages.items[1].textTaggedUsers[0].tag).toBe(`@${theirUsername}`)
  expect(resp.data.chat.messages.items[1].textTaggedUsers[0].user.userId).toBe(theirUserId)
  expect(resp.data.chat.messages.items[2].textTaggedUsers).toHaveLength(0)
})

test('Edit chat message', async () => {
  const [ourClient, ourUserId, , , ourUsername] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()
  const [randoClient] = await loginCache.getCleanLogin()

  // they open up a chat with us
  const [chatId, messageId, orgText] = [uuidv4(), uuidv4(), 'lore org']
  let variables = {userId: ourUserId, chatId, messageId, messageText: orgText}
  let resp = await theirClient.mutate({mutation: mutations.createDirectChat, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.createDirectChat.chatId).toBe(chatId)

  // verify neither rando nor us can edit the chat message
  variables = {messageId, text: 'lore new'}
  await expect(randoClient.mutate({mutation: mutations.editChatMessage, variables})).rejects.toThrow(
    /ClientError: User .* cannot edit message /,
  )
  await expect(ourClient.mutate({mutation: mutations.editChatMessage, variables})).rejects.toThrow(
    /ClientError: User .* cannot edit message /,
  )

  // we report a view of the message
  variables = {messageIds: [messageId]}
  resp = await ourClient.mutate({mutation: mutations.reportChatMessageViews, variables})
  expect(resp.errors).toBeUndefined()

  // check the message hasn't changed
  resp = await ourClient.query({query: queries.chat, variables: {chatId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.chat.chatId).toBe(chatId)
  expect(resp.data.chat.messages.items).toHaveLength(1)
  expect(resp.data.chat.messages.items[0].messageId).toBe(messageId)
  expect(resp.data.chat.messages.items[0].text).toBe(orgText)
  expect(resp.data.chat.messages.items[0].textTaggedUsers).toEqual([])
  expect(resp.data.chat.messages.items[0].lastEditedAt).toBeNull()
  expect(resp.data.chat.messages.items[0].viewedStatus).toBe('VIEWED')

  // check they *can* edit the message
  let newText = `lore new, @${ourUsername}`
  let before = moment().toISOString()
  resp = await theirClient.mutate({mutation: mutations.editChatMessage, variables: {messageId, text: newText}})
  let after = moment().toISOString()
  expect(resp.errors).toBeUndefined()
  expect(resp.data.editChatMessage.messageId).toBe(messageId)
  expect(resp.data.editChatMessage.text).toBe(newText)
  expect(resp.data.editChatMessage.textTaggedUsers).toHaveLength(1)
  expect(resp.data.editChatMessage.textTaggedUsers[0].tag).toBe(`@${ourUsername}`)
  expect(resp.data.editChatMessage.textTaggedUsers[0].user.userId).toBe(ourUserId)
  expect(resp.data.editChatMessage.viewedStatus).toBe('VIEWED')
  const lastEditedAt = resp.data.editChatMessage.lastEditedAt
  expect(before <= lastEditedAt).toBe(true)
  expect(after >= lastEditedAt).toBe(true)
  const message = resp.data.editChatMessage

  // check that really stuck in db
  resp = await theirClient.query({query: queries.chat, variables: {chatId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.chat.chatId).toBe(chatId)
  expect(resp.data.chat.messages.items).toHaveLength(1)
  expect(resp.data.chat.messages.items[0]).toEqual(message)

  // check when we see the message, the viewed status still reflects that we have seen the message
  // even though we haven't seen the edit
  resp = await ourClient.query({query: queries.chat, variables: {chatId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.chat.chatId).toBe(chatId)
  expect(resp.data.chat.messages.items).toHaveLength(1)
  expect(resp.data.chat.messages.items[0].messageId).toBe(messageId)
  expect(resp.data.chat.messages.items[0].viewedStatus).toBe('VIEWED')
})

test('Delete chat message', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()
  const [randoClient] = await loginCache.getCleanLogin()

  // they open up a chat with us
  const [chatId, messageId, orgText] = [uuidv4(), uuidv4(), 'lore org']
  let variables = {userId: ourUserId, chatId, messageId, messageText: orgText}
  let resp = await theirClient.mutate({mutation: mutations.createDirectChat, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.createDirectChat.chatId).toBe(chatId)

  // verify neither rando nor us can delete the chat message
  variables = {messageId: uuidv4()}
  await expect(randoClient.mutate({mutation: mutations.deleteChatMessage, variables})).rejects.toThrow(
    /ClientError: User .* cannot delete message /,
  )
  await expect(ourClient.mutate({mutation: mutations.deleteChatMessage, variables})).rejects.toThrow(
    /ClientError: User .* cannot delete message /,
  )

  // check the message hasn't changed
  resp = await theirClient.query({query: queries.chat, variables: {chatId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.chat.chatId).toBe(chatId)
  expect(resp.data.chat.messages.items).toHaveLength(1)
  expect(resp.data.chat.messages.items[0].messageId).toBe(messageId)

  // check they *can* delete the message
  resp = await theirClient.mutate({mutation: mutations.deleteChatMessage, variables: {messageId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.deleteChatMessage.messageId).toBe(messageId)
  await misc.sleep(2000) // let dynamo converge

  // check that the message has now dissapeared from the db
  resp = await theirClient.query({query: queries.chat, variables: {chatId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.chat.chatId).toBe(chatId)
  expect(resp.data.chat.messageCount).toBe(0)
  expect(resp.data.chat.messages.items).toHaveLength(0)
})

test('User.chats sort order should react to message adds, edits and not deletes', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [other1Client] = await loginCache.getCleanLogin()
  const [other2Client] = await loginCache.getCleanLogin()

  // other1 opens up a chat with us
  const [chatId1, messageId11] = [uuidv4(), uuidv4()]
  let variables = {userId: ourUserId, chatId: chatId1, messageId: messageId11, messageText: 'lore ipsum'}
  let resp = await other1Client.mutate({mutation: mutations.createDirectChat, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.createDirectChat.chatId).toBe(chatId1)

  // other2 opens up a chat with us
  const [chatId2, messageId21] = [uuidv4(), uuidv4()]
  variables = {userId: ourUserId, chatId: chatId2, messageId: messageId21, messageText: 'lore ipsum'}
  resp = await other2Client.mutate({mutation: mutations.createDirectChat, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.createDirectChat.chatId).toBe(chatId2)

  // verify we see both those chats in correct order
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.chats.items).toHaveLength(2)
  expect(resp.data.self.chats.items[0].chatId).toBe(chatId2)
  expect(resp.data.self.chats.items[1].chatId).toBe(chatId1)

  // other1 edits their original message
  variables = {messageId: messageId11, text: 'lore ipsum for reals'}
  resp = await other1Client.mutate({mutation: mutations.editChatMessage, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.editChatMessage.messageId).toBe(messageId11)

  // verify the order we see chats in has now changed
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.chats.items).toHaveLength(2)
  expect(resp.data.self.chats.items[0].chatId).toBe(chatId1)
  expect(resp.data.self.chats.items[1].chatId).toBe(chatId2)

  // other2 deletes their original message
  variables = {messageId: messageId21}
  resp = await other2Client.mutate({mutation: mutations.deleteChatMessage, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.deleteChatMessage.messageId).toBe(messageId21)

  // verify the order we see chats in has not changed - deletes aren't counted as new activity
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.chats.items).toHaveLength(2)
  expect(resp.data.self.chats.items[0].chatId).toBe(chatId1)
  expect(resp.data.self.chats.items[1].chatId).toBe(chatId2)

  // we add another message to chat1
  const messageId13 = uuidv4()
  variables = {chatId: chatId1, messageId: messageId13, text: 'new text'}
  resp = await ourClient.mutate({mutation: mutations.addChatMessage, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addChatMessage.messageId).toBe(messageId13)

  // verify the order we see chats in has _not_ changed
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.chats.items).toHaveLength(2)
  expect(resp.data.self.chats.items[0].chatId).toBe(chatId1)
  expect(resp.data.self.chats.items[1].chatId).toBe(chatId2)
})
