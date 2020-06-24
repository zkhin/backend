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

  // we start a direct chat with them
  const chatId = uuidv4()
  let variables = {userId: theirUserId, chatId, messageId: uuidv4(), messageText: 'lore ipsum'}
  let resp = await ourClient.mutate({mutation: mutations.createDirectChat, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.createDirectChat.chatId).toBe(chatId)

  // verify no card generated for the chat we created or that first message
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(0)
  expect(resp.data.self.cards.items).toHaveLength(0)

  // they add a message to the chat
  const messageId = uuidv4()
  variables = {chatId, messageId, text: 'lore ipsum'}
  resp = await theirClient.mutate({mutation: mutations.addChatMessage, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addChatMessage.messageId).toBe(messageId)

  // verify a card was generated for their chat message
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(1)
  expect(resp.data.self.cards.items).toHaveLength(1)

  // verify that card has expected format
  let card = resp.data.self.cards.items[0]
  expect(card.cardId).toBeTruthy()
  expect(card.title).toBe('You have new messages')
  expect(card.subTitle).toBeNull()
  expect(card.action).toBe('https://real.app/chat/')
  expect(card.thumbnail).toBeFalsy()

  // they add another message to the chat
  variables = {chatId, messageId: uuidv4(), text: 'lore ipsum'}
  resp = await ourClient.mutate({mutation: mutations.addChatMessage, variables})
  expect(resp.errors).toBeUndefined()

  // verify we still have just one card
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(1)
  expect(resp.data.self.cards.items).toHaveLength(1)

  // we report to have viewed a chat doesn't matter which
  resp = await ourClient.mutate({mutation: mutations.reportChatViews, variables: {chatIds: [chatId]}})
  expect(resp.errors).toBeUndefined()

  // verify the card has disappeared
  await misc.sleep(500)
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(0)
  expect(resp.data.self.cards.items).toHaveLength(0)
})
