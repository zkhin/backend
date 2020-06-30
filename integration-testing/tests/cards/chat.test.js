/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito')
const misc = require('../../utils/misc')
const {mutations, queries} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Unread chat message card with correct format', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we start a direct chat with them, verify no card generated for the chat we created or that first message
  const chatId = uuidv4()
  await ourClient
    .mutate({
      mutation: mutations.createDirectChat,
      variables: {userId: theirUserId, chatId, messageId: uuidv4(), messageText: 'lore ipsum'},
    })
    .then(({data}) => expect(data.createDirectChat.chatId).toBe(chatId))
  await misc.sleep(2000)
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(0)
    expect(data.self.cards.items).toHaveLength(0)
  })

  // they add a message to the chat, verify a card was generated for their chat message, has correct format
  await theirClient
    .mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: uuidv4(), text: 'lore ipsum'}})
    .then(({data}) => expect(data.addChatMessage.messageId).toBeTruthy())
  await misc.sleep(2000)
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    expect(data.self.cards.items[0].cardId).toBeTruthy()
    expect(data.self.cards.items[0].title).toBe('You have 1 chat with new messages')
    expect(data.self.cards.items[0].subTitle).toBeNull()
    expect(data.self.cards.items[0].action).toBe('https://real.app/chat/')
    expect(data.self.cards.items[0].thumbnail).toBeFalsy()
  })

  // they add another message to the chat, verify card title has not changed
  await ourClient
    .mutate({
      mutation: mutations.addChatMessage,
      variables: {chatId, messageId: uuidv4(), text: 'lore ipsum'},
    })
    .then(({data}) => expect(data.addChatMessage.messageId).toBeTruthy())
  await misc.sleep(2000)
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    expect(data.self.cards.items[0].title).toBe('You have 1 chat with new messages')
  })

  // they open up a group chat with us, verify our card title changes
  const chatId2 = uuidv4()
  await ourClient
    .mutate({
      mutation: mutations.createGroupChat,
      variables: {chatId: chatId2, userIds: [ourUserId, theirUserId], messageId: uuidv4(), messageText: 'm1'},
    })
    .then(({data}) => expect(data.createGroupChat.chatId).toBe(chatId2))
  await misc.sleep(2000)
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    expect(data.self.cards.items[0].title).toBe('You have 2 chats with new messages')
  })

  // we report to have viewed one of the chats, verify our card title has changed
  await ourClient.mutate({mutation: mutations.reportChatViews, variables: {chatIds: [chatId]}})
  await misc.sleep(2000)
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    expect(data.self.cards.items[0].title).toBe('You have 1 chat with new messages')
  })

  // we report to have viewed the other chat, verify card has dissapeared
  await ourClient.mutate({mutation: mutations.reportChatViews, variables: {chatIds: [chatId2]}})
  // verify the card has disappeared
  await misc.sleep(2000)
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(0)
    expect(data.self.cards.items).toHaveLength(0)
  })
})
