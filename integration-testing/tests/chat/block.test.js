/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const schema = require('../../utils/schema.js')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Blocking a user causes our direct chat with them to disappear to both of us', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // they open up a chat with us
  const [chatId, messageId1, text1] = [uuidv4(), uuidv4(), 'hey this is msg 1']
  let variables = {userId: ourUserId, chatId, messageId: messageId1, messageText: text1}
  let resp = await theirClient.mutate({mutation: schema.createDirectChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createDirectChat']['chatId']).toBe(chatId)

  // check we can see the chat
  resp = await ourClient.query({query: schema.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)

  // check the chat appears in their list of chats
  resp = await theirClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['chatCount']).toBe(1)
  expect(resp['data']['self']['chats']['items']).toHaveLength(1)
  expect(resp['data']['self']['chats']['items'][0]['chatId']).toBe(chatId)

  // we block them
  resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(theirUserId)
  expect(resp['data']['blockUser']['blockedStatus']).toBe('BLOCKING')

  // check neither of us can directly see the chat anymore
  resp = await ourClient.query({query: schema.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']).toBeNull()

  resp = await theirClient.query({query: schema.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']).toBeNull()

  // check neither of us see the chat by looking at each other's profiles
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['directChat']).toBeNull()

  resp = await ourClient.query({query: schema.user, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['directChat']).toBeNull()

  // check niether of us see the chat in our list of chats
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['chatCount']).toBe(0)
  expect(resp['data']['self']['chats']['items']).toHaveLength(0)

  resp = await theirClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['chatCount']).toBe(0)
  expect(resp['data']['self']['chats']['items']).toHaveLength(0)
})


test('Cannot open a direct chat with a user that blocks us or that we block', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we block them
  let resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(theirUserId)
  expect(resp['data']['blockUser']['blockedStatus']).toBe('BLOCKING')

  // check they cannot open up a direct chat with us
  const chatVars = {chatId: uuidv4(), messageId: uuidv4(), messageText: 'lore ipsum'}
  let variables = {userId: ourUserId, ...chatVars}
  await expect(theirClient.mutate({mutation: schema.createDirectChat, variables})).rejects.toThrow('ClientError')

  // check we cannot open up a direct chat with them
  variables = {userId: theirUserId, ...chatVars}
  await expect(ourClient.mutate({mutation: schema.createDirectChat, variables})).rejects.toThrow('ClientError')
})
