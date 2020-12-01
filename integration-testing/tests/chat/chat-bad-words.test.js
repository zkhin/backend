const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito')
const misc = require('../../utils/misc')
const {mutations, queries} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()
jest.retryTimes(1)

let anonClient
beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())
afterEach(async () => {
  if (anonClient) await anonClient.mutate({mutation: mutations.deleteUser})
  anonClient = null
})

test('Create a direct chat with bad word', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // check we have no direct chat between us
  let resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.directChat).toBeNull()
  expect(resp.data.self.chatCount).toBe(0)
  expect(resp.data.self.chats.items).toHaveLength(0)

  resp = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp.data.user.directChat).toBeNull()
  expect(resp.data.user.chatCount).toBeNull()
  expect(resp.data.user.chats).toBeNull()

  resp = await ourClient.query({query: queries.user, variables: {userId: theirUserId}})
  expect(resp.data.user.directChat).toBeNull()
  expect(resp.data.user.chatCount).toBeNull()
  expect(resp.data.user.chats).toBeNull()

  // we open up a direct chat with them
  const [chatId, messageId] = [uuidv4(), uuidv4()]
  const messageText = 'lore ipsum'
  let variables = {userId: theirUserId, chatId, messageId, messageText}

  await ourClient
    .mutate({mutation: mutations.createDirectChat, variables})
    .then(({data: {createDirectChat: chat}}) => {
      expect(chat.chatId).toBe(chatId)
      expect(chat.chatType).toBe('DIRECT')
      expect(chat.name).toBeNull()
      expect(chat.userCount).toBe(2)
      expect(chat.usersCount).toBe(2)
      expect(chat.users.items.map((u) => u.userId).sort()).toEqual([ourUserId, theirUserId].sort())
      expect(chat.messages.items).toHaveLength(1)
      expect(chat.messages.items[0].messageId).toBe(messageId)
      expect(chat.messages.items[0].text).toBe(messageText)
      expect(chat.messages.items[0].chat.chatId).toBe(chatId)
      expect(chat.messages.items[0].author.userId).toBe(ourUserId)
      expect(chat.messages.items[0].viewedStatus).toBe('VIEWED')
    })

  // check we see the chat in our list of chats
  await ourClient.query({query: queries.user, variables: {userId: ourUserId}}).then(({data: {user}}) => {
    expect(user.directChat).toBeNull()
    expect(user.chatCount).toBe(1)
    expect(user.chats.items).toHaveLength(1)
    expect(user.chats.items[0].chatId).toBe(chatId)
  })

  // check they see the chat in their list of chats
  await theirClient.query({query: queries.user, variables: {userId: theirUserId}}).then(({data: {user}}) => {
    expect(user.directChat).toBeNull()
    expect(user.chatCount).toBe(1)
    expect(user.chats.items).toHaveLength(1)
    expect(user.chats.items[0].chatId).toBe(chatId)
  })

  // check we can both see the chat directly
  await ourClient.query({query: queries.chat, variables: {chatId}}).then(({data: {chat}}) => {
    expect(chat.chatId).toBe(chatId)
  })

  await theirClient.query({query: queries.chat, variables: {chatId}}).then(({data: {chat}}) => {
    expect(chat.chatId).toBe(chatId)
  })

  // they add chat message with bad word, verify it's removed
  const [messageId2, text2] = [uuidv4(), 'msg skype']
  variables = {chatId, messageId: messageId2, text: text2}
  await theirClient
    .mutate({mutation: mutations.addChatMessage, variables})
    .then(({data: {addChatMessage: chatMessage}}) => {
      expect(chatMessage.messageId).toBe(messageId2)
      expect(chatMessage.text).toBe(text2)
      expect(chatMessage.chat.chatId).toBe(chatId)
    })

  // verify the bad word chat is removed
  await misc.sleep(1000)
  await ourClient.query({query: queries.user, variables: {userId: ourUserId}}).then(({data: {user}}) => {
    expect(user.chatCount).toBe(1)
    expect(user.chats.items).toHaveLength(1)
    expect(user.chats.items[0].chatId).toBe(chatId)
  })
  await ourClient.query({query: queries.chat, variables: {chatId}}).then(({data: {chat}}) => {
    expect(chat.chatId).toBe(chatId)
    expect(chat.messages.items).toHaveLength(1)
  })

  // // edit the message, verify it's removed
  // await ourClient
  //   .mutate({mutation: mutations.editChatMessage, variables: {messageId, text: 'hello world skype'}})
  //   .then(({data: {editChatMessage: chatMessage}}) => {
  //     expect(chatMessage.messageId).toBe(messageId)
  //     expect(chatMessage.text).toBe('hello world skype')
  //     expect(chatMessage.chat.chatId).toBe(chatId)
  //   })

  // // verify the bad word chat is removed
  // await misc.sleep(2000)
  // await ourClient.query({query: queries.user, variables: {userId: ourUserId}}).then(({data: {user}}) => {
  //   console.log(user.chatCount)
  //   console.log(user.chats)
  //   // expect(user.chatCount).toBe(1)
  //   // expect(user.chats.items).toHaveLength(1)
  //   // expect(user.chats.items[0].chatId).toBe(chatId)
  // })
  // await ourClient.query({query: queries.chat, variables: {chatId}}).then(({data: {chat}}) => {
  //   console.log(chat.messages)
  //   expect(chat.chatId).toBe(chatId)
  //   expect(chat.messages.items).toHaveLength(1)
  // })
})
