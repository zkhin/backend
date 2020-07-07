/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito')
const misc = require('../../utils/misc')
const {mutations, queries} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Flag message failures', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [other1Client, other1UserId] = await loginCache.getCleanLogin()
  const [other2Client] = await loginCache.getCleanLogin()
  const mutation = mutations.flagChatMessage

  // we create a group chat with us and other1 in it
  const [chatId, messageId1] = [uuidv4(), uuidv4()]
  const systemMessageId = await ourClient
    .mutate({
      mutation: mutations.createGroupChat,
      variables: {chatId, userIds: [other1UserId], messageId: messageId1, messageText: 'm1'},
    })
    .then(({data}) => {
      expect(data.createGroupChat.chatId).toBe(chatId)
      expect(data.createGroupChat.messages.items[2].messageId).toBe(messageId1)
      return data.createGroupChat.messages.items[0].messageId
    })

  // other1 adds a message
  const messageId2 = uuidv4()
  await other1Client
    .mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: messageId2, text: 'm2'}})
    .then(({data}) => expect(data.addChatMessage.messageId).toBe(messageId2))

  // can't flag a message that DNE
  const messageId3 = uuidv4()
  await expect(other1Client.mutate({mutation, variables: {messageId: messageId3}})).rejects.toThrow(
    /ChatMessage .* does not exist/,
  )

  // cant' flag a system message
  await expect(ourClient.mutate({mutation, variables: {messageId: systemMessageId}})).rejects.toThrow(
    /Cannot flag system chat message/,
  )

  // can't flag our own message
  await expect(ourClient.mutate({mutation, variables: {messageId: messageId1}})).rejects.toThrow(
    /User cant flag their own/,
  )

  // can't flag message of a chat user is not in
  await expect(other2Client.mutate({mutation, variables: {messageId: messageId1}})).rejects.toThrow(
    /User is not part of chat/,
  )

  // blocking relationships block flagging both ways
  await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: other1UserId}}).then(({data}) => {
    expect(data.blockUser.userId).toBe(other1UserId)
    expect(data.blockUser.blockedStatus).toBe('BLOCKING')
  })
  await expect(ourClient.mutate({mutation, variables: {messageId: messageId2}})).rejects.toThrow(
    /User has blocked owner of chatMessage/,
  )
  await expect(other1Client.mutate({mutation, variables: {messageId: messageId1}})).rejects.toThrow(
    /User has been blocked by owner of chatMessage/,
  )
  await ourClient.mutate({mutation: mutations.unblockUser, variables: {userId: other1UserId}}).then(({data}) => {
    expect(data.unblockUser.userId).toBe(other1UserId)
    expect(data.unblockUser.blockedStatus).toBe('NOT_BLOCKING')
  })

  // can't flag a message if we're disabled
  await other1Client.mutate({mutation: mutations.disableUser}).then(({data}) => {
    expect(data.disableUser.userId).toBe(other1UserId)
    expect(data.disableUser.userStatus).toBe('DISABLED')
  })
  await expect(other1Client.mutate({mutation, variables: {messageId: messageId1}})).rejects.toThrow(
    /User .* is not ACTIVE/,
  )

  // can't double flag message
  await ourClient.mutate({mutation, variables: {messageId: messageId2}}).then(({data}) => {
    expect(data.flagChatMessage.messageId).toBe(messageId2)
    expect(data.flagChatMessage.flagStatus).toBe('FLAGGED')
  })
  await expect(ourClient.mutate({mutation, variables: {messageId: messageId2}})).rejects.toThrow(
    /ChatMessage .* has already been flagged by user/,
  )
})

test('Flag message success', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we create a direct chat with them
  const [chatId, messageId] = [uuidv4(), uuidv4()]
  await ourClient
    .mutate({
      mutation: mutations.createDirectChat,
      variables: {userId: theirUserId, chatId, messageId, messageText: 'lore ipsum'},
    })
    .then(({data}) => expect(data.createDirectChat.messages.items.map((i) => i.messageId)).toContain(messageId))

  // check they see our message as unflagged
  await theirClient.query({query: queries.chat, variables: {chatId}}).then(({data}) => {
    expect(data.chat.messages.items[0].messageId).toBe(messageId)
    expect(data.chat.messages.items[0].flagStatus).toBe('NOT_FLAGGED')
  })

  // they flag our message
  await theirClient.mutate({mutation: mutations.flagChatMessage, variables: {messageId}}).then(({data}) => {
    expect(data.flagChatMessage.messageId).toBe(messageId)
    expect(data.flagChatMessage.flagStatus).toBe('FLAGGED')
  })

  // check they see our message as flagged now
  await misc.sleep(2000)
  await theirClient.query({query: queries.chat, variables: {chatId}}).then(({data}) => {
    expect(data.chat.messages.items[0].messageId).toBe(messageId)
    expect(data.chat.messages.items[0].flagStatus).toBe('FLAGGED')
  })
})
