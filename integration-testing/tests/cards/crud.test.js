/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const {mutations, queries} = require('../../schema')
const misc = require('../../utils/misc')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Cards are private to user themselves', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // verify we see our zero cards and count on self
  let resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(0)
  expect(resp.data.self.cards.items).toHaveLength(0)

  // verify we see our zero cards and count on user
  resp = await ourClient.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.userId).toBe(ourUserId)
  expect(resp.data.user.cardCount).toBe(0)
  expect(resp.data.user.cards.items).toHaveLength(0)

  // verify they don't see our zero cards and count
  resp = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.userId).toBe(ourUserId)
  expect(resp.data.user.cardCount).toBeNull()
  expect(resp.data.user.cards).toBeNull()
})

test('List cards', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // verify list & count for no cards
  let resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(0)
  expect(resp.data.self.cards.items).toHaveLength(0)

  // they start a direct chat with us
  const chatId = uuidv4()
  let variables = {userId: ourUserId, chatId, messageId: uuidv4(), messageText: 'lore ipsum'}
  resp = await theirClient.mutate({mutation: mutations.createDirectChat, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.createDirectChat.chatId).toBe(chatId)

  // verify list & count that one card
  await misc.sleep(500) // let dynamo stream handler catch up
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(1)
  expect(resp.data.self.cards.items).toHaveLength(1)

  // we add a post
  const postId = uuidv4()
  variables = {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)

  // they comment on our post
  variables = {commentId: uuidv4(), postId, text: 'nice post'}
  resp = await theirClient.mutate({mutation: mutations.addComment, variables})
  expect(resp.errors).toBeUndefined()

  // verify list & count for those two cards, including order (most recent first)
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(2)
  expect(resp.data.self.cards.items).toHaveLength(2)
  expect(resp.data.self.cards.items[0].action).toContain('chat')
  expect(resp.data.self.cards.items[1].action).toContain('chat')
})

test('Delete card, generate new card after deleting', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // verify can't delete card that doesn't exist
  await expect(ourClient.mutate({mutation: mutations.deleteCard, variables: {cardId: uuidv4()}})).rejects.toThrow(
    /ClientError: No card .* found/,
  )

  // they start a direct chat with us
  const chatId = uuidv4()
  let variables = {userId: ourUserId, chatId, messageId: uuidv4(), messageText: 'lore ipsum'}
  let resp = await theirClient.mutate({mutation: mutations.createDirectChat, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.createDirectChat.chatId).toBe(chatId)
  await misc.sleep(2000) // let dynamo converge

  // verify we see the card, and its count
  await misc.sleep(500) // let dynamo stream handler catch up
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(1)
  expect(resp.data.self.cards.items).toHaveLength(1)
  expect(resp.data.self.cards.items[0].cardId).toBeTruthy()
  expect(resp.data.self.cards.items[0].cardId).toBeTruthy()
  const card = resp.data.self.cards.items[0]

  // verify they can't delete our card
  await expect(
    theirClient.mutate({mutation: mutations.deleteCard, variables: {cardId: card.cardId}}),
  ).rejects.toThrow(/ClientError: Caller.* does not own Card /)

  // verify we can delete our card
  resp = await ourClient.mutate({mutation: mutations.deleteCard, variables: {cardId: card.cardId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.deleteCard).toEqual(card)

  // verify the card and its count are gone
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(0)
  expect(resp.data.self.cards.items).toHaveLength(0)

  // they add a message
  variables = {chatId, messageId: uuidv4(), text: 'lore ipsum'}
  resp = await theirClient.mutate({mutation: mutations.addChatMessage, variables})
  expect(resp.errors).toBeUndefined()

  // verify we see the card and it's exactly like the old card (even same cardId)
  await misc.sleep(500) // let dynamo stream handler catch up
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(1)
  expect(resp.data.self.cards.items).toHaveLength(1)
  expect(resp.data.self.cards.items[0]).toEqual(card)
})
