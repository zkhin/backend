/* eslint-env jest */

const moment = require('moment')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const schema = require('../../utils/schema.js')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Add messages to a direct chat', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // they open up a chat with us
  const [chatId, messageId1, text1] = [uuidv4(), uuidv4(), 'hey this is msg 1']
  let variables = {userId: ourUserId, chatId, messageId: messageId1, messageText: text1}
  let resp = await theirClient.mutate({mutation: schema.createDirectChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createDirectChat']['chatId']).toBe(chatId)
  expect(resp['data']['createDirectChat']['messages']['items']).toHaveLength(1)
  expect(resp['data']['createDirectChat']['messages']['items'][0]['messageId']).toBe(messageId1)
  expect(resp['data']['createDirectChat']['messages']['items'][0]['text']).toBe(text1)

  // we add two messages to the chat
  const [messageId2, text2] = [uuidv4(), 'msg 2']
  variables = {chatId, messageId: messageId2, text: text2}
  resp = await ourClient.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId2)
  expect(resp['data']['addChatMessage']['text']).toBe(text2)
  expect(resp['data']['addChatMessage']['chat']['chatId']).toBe(chatId)

  const [messageId3, text3] = [uuidv4(), 'msg 3']
  variables = {chatId, messageId: messageId3, text: text3}
  resp = await ourClient.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId3)
  expect(resp['data']['addChatMessage']['text']).toBe(text3)
  expect(resp['data']['addChatMessage']['chat']['chatId']).toBe(chatId)

  // they add another message to the chat, check the timestamp
  const [messageId4, text4] = [uuidv4(), 'msg 4']
  variables = {chatId, messageId: messageId4, text: text4}
  let before = moment().toISOString()
  resp = await theirClient.mutate({mutation: schema.addChatMessage, variables})
  let after = moment().toISOString()
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId4)
  expect(resp['data']['addChatMessage']['text']).toBe(text4)
  expect(resp['data']['addChatMessage']['chat']['chatId']).toBe(chatId)
  const lastMessageCreatedAt = resp['data']['addChatMessage']['createdAt']
  expect(before <= lastMessageCreatedAt).toBe(true)
  expect(after >= lastMessageCreatedAt).toBe(true)

  // check we see all the messages are there in the expected order
  resp = await ourClient.query({query: schema.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['chat']['lastMessageAt']).toBe(lastMessageCreatedAt)
  expect(resp['data']['chat']['messageCount']).toBe(4)
  expect(resp['data']['chat']['messages']['items']).toHaveLength(4)
  expect(resp['data']['chat']['messages']['items'][0]['messageId']).toBe(messageId1)
  expect(resp['data']['chat']['messages']['items'][1]['messageId']).toBe(messageId2)
  expect(resp['data']['chat']['messages']['items'][2]['messageId']).toBe(messageId3)
  expect(resp['data']['chat']['messages']['items'][3]['messageId']).toBe(messageId4)
  expect(resp['data']['chat']['messages']['items'][0]['text']).toBe(text1)
  expect(resp['data']['chat']['messages']['items'][1]['text']).toBe(text2)
  expect(resp['data']['chat']['messages']['items'][2]['text']).toBe(text3)
  expect(resp['data']['chat']['messages']['items'][3]['text']).toBe(text4)
  expect(resp['data']['chat']['messages']['items'][0]['author']['userId']).toBe(theirUserId)
  expect(resp['data']['chat']['messages']['items'][1]['author']['userId']).toBe(ourUserId)
  expect(resp['data']['chat']['messages']['items'][2]['author']['userId']).toBe(ourUserId)
  expect(resp['data']['chat']['messages']['items'][3]['author']['userId']).toBe(theirUserId)
  expect(resp['data']['chat']['messages']['items'][0]['viewedStatus']).toBe('NOT_VIEWED')
  expect(resp['data']['chat']['messages']['items'][1]['viewedStatus']).toBe('VIEWED')
  expect(resp['data']['chat']['messages']['items'][2]['viewedStatus']).toBe('VIEWED')
  expect(resp['data']['chat']['messages']['items'][3]['viewedStatus']).toBe('NOT_VIEWED')

  // check they can also see them, and in reverse order if they want
  resp = await theirClient.query({query: schema.chat, variables: {chatId, reverse: true}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['chat']['lastMessageAt']).toBe(lastMessageCreatedAt)
  expect(resp['data']['chat']['messageCount']).toBe(4)
  expect(resp['data']['chat']['messages']['items']).toHaveLength(4)
  expect(resp['data']['chat']['messages']['items'][0]['messageId']).toBe(messageId4)
  expect(resp['data']['chat']['messages']['items'][1]['messageId']).toBe(messageId3)
  expect(resp['data']['chat']['messages']['items'][2]['messageId']).toBe(messageId2)
  expect(resp['data']['chat']['messages']['items'][3]['messageId']).toBe(messageId1)
  expect(resp['data']['chat']['messages']['items'][0]['viewedStatus']).toBe('VIEWED')
  expect(resp['data']['chat']['messages']['items'][1]['viewedStatus']).toBe('NOT_VIEWED')
  expect(resp['data']['chat']['messages']['items'][2]['viewedStatus']).toBe('NOT_VIEWED')
  expect(resp['data']['chat']['messages']['items'][3]['viewedStatus']).toBe('VIEWED')
})


test('Report message views', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()
  const [chatId, messageId1, messageId2, messageId3] = [uuidv4(), uuidv4(), uuidv4(), uuidv4()]

  // they open up a chat with us
  let variables = {userId: ourUserId, chatId, messageId: messageId1, messageText: 'lore'}
  let resp = await theirClient.mutate({mutation: schema.createDirectChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createDirectChat']['chatId']).toBe(chatId)
  expect(resp['data']['createDirectChat']['messages']['items']).toHaveLength(1)
  expect(resp['data']['createDirectChat']['messages']['items'][0]['messageId']).toBe(messageId1)
  expect(resp['data']['createDirectChat']['messages']['items'][0]['viewedStatus']).toBe('VIEWED')

  // we add two messages to the chat
  variables = {chatId, messageId: messageId2, text: 'lore'}
  resp = await ourClient.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId2)
  expect(resp['data']['addChatMessage']['viewedStatus']).toBe('VIEWED')

  variables = {chatId, messageId: messageId3, text: 'lore'}
  resp = await ourClient.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId3)
  expect(resp['data']['addChatMessage']['viewedStatus']).toBe('VIEWED')

  // check each message's viewedStatus is as expected for both of us
  resp = await ourClient.query({query: schema.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['chat']['messageCount']).toBe(3)
  expect(resp['data']['chat']['messages']['items']).toHaveLength(3)
  expect(resp['data']['chat']['messages']['items'][0]['messageId']).toBe(messageId1)
  expect(resp['data']['chat']['messages']['items'][1]['messageId']).toBe(messageId2)
  expect(resp['data']['chat']['messages']['items'][2]['messageId']).toBe(messageId3)
  expect(resp['data']['chat']['messages']['items'][0]['viewedStatus']).toBe('NOT_VIEWED')
  expect(resp['data']['chat']['messages']['items'][1]['viewedStatus']).toBe('VIEWED')
  expect(resp['data']['chat']['messages']['items'][2]['viewedStatus']).toBe('VIEWED')

  resp = await theirClient.query({query: schema.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['chat']['messageCount']).toBe(3)
  expect(resp['data']['chat']['messages']['items']).toHaveLength(3)
  expect(resp['data']['chat']['messages']['items'][0]['messageId']).toBe(messageId1)
  expect(resp['data']['chat']['messages']['items'][1]['messageId']).toBe(messageId2)
  expect(resp['data']['chat']['messages']['items'][2]['messageId']).toBe(messageId3)
  expect(resp['data']['chat']['messages']['items'][0]['viewedStatus']).toBe('VIEWED')
  expect(resp['data']['chat']['messages']['items'][1]['viewedStatus']).toBe('NOT_VIEWED')
  expect(resp['data']['chat']['messages']['items'][2]['viewedStatus']).toBe('NOT_VIEWED')

  // we report to have viewed the first message (and one we've already viewed, which should be a no-op)
  variables = {messageIds: [messageId1, messageId2]}
  resp = await ourClient.mutate({mutation: schema.reportChatMessageViews, variables})
  expect(resp['errors']).toBeUndefined()

  // check we have now viewed all messages
  resp = await ourClient.query({query: schema.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['chat']['messageCount']).toBe(3)
  expect(resp['data']['chat']['messages']['items']).toHaveLength(3)
  expect(resp['data']['chat']['messages']['items'][0]['messageId']).toBe(messageId1)
  expect(resp['data']['chat']['messages']['items'][1]['messageId']).toBe(messageId2)
  expect(resp['data']['chat']['messages']['items'][2]['messageId']).toBe(messageId3)
  expect(resp['data']['chat']['messages']['items'][0]['viewedStatus']).toBe('VIEWED')
  expect(resp['data']['chat']['messages']['items'][1]['viewedStatus']).toBe('VIEWED')
  expect(resp['data']['chat']['messages']['items'][2]['viewedStatus']).toBe('VIEWED')

  // they report they have viewed the two message they haven't viewed
  variables = {messageIds: [messageId2, messageId3]}
  resp = await theirClient.mutate({mutation: schema.reportChatMessageViews, variables})
  expect(resp['errors']).toBeUndefined()

  // check they have now viewed all messages
  resp = await theirClient.query({query: schema.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['chat']['messageCount']).toBe(3)
  expect(resp['data']['chat']['messages']['items']).toHaveLength(3)
  expect(resp['data']['chat']['messages']['items'][0]['messageId']).toBe(messageId1)
  expect(resp['data']['chat']['messages']['items'][1]['messageId']).toBe(messageId2)
  expect(resp['data']['chat']['messages']['items'][2]['messageId']).toBe(messageId3)
  expect(resp['data']['chat']['messages']['items'][0]['viewedStatus']).toBe('VIEWED')
  expect(resp['data']['chat']['messages']['items'][1]['viewedStatus']).toBe('VIEWED')
  expect(resp['data']['chat']['messages']['items'][2]['viewedStatus']).toBe('VIEWED')
})


test('Cant add a message to a chat we are not in', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()
  const [randoClient] = await loginCache.getCleanLogin()
  const [chatId, messageId] = [uuidv4(), uuidv4()]

  // they open up a chat with us
  let variables = {userId: ourUserId, chatId, messageId, messageText: 'lore'}
  let resp = await theirClient.mutate({mutation: schema.createDirectChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createDirectChat']['chatId']).toBe(chatId)

  // verify the rando can't add a message to our chat
  variables = {chatId, messageId: uuidv4(), text: 'lore'}
  await expect(randoClient.mutate({mutation: schema.addChatMessage, variables})).rejects.toThrow('ClientError')

  // check the chat and verify the rando's message didn't get saved
  resp = await ourClient.query({query: schema.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['chat']['messageCount']).toBe(1)
  expect(resp['data']['chat']['messages']['items']).toHaveLength(1)
  expect(resp['data']['chat']['messages']['items'][0]['messageId']).toBe(messageId)
})


test('Tag users in a chat message', async () => {
  const [ourClient, ourUserId, , , ourUsername] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId, , , theirUsername] = await loginCache.getCleanLogin()
  const [chatId, messageId1, messageId2, messageId3] = [uuidv4(), uuidv4(), uuidv4(), uuidv4()]

  // they open up a chat with us, with a tags in the message
  let text = `hi @${theirUsername}! hi from @${ourUsername}`
  let variables = {userId: ourUserId, chatId, messageId: messageId1, messageText: text}
  let resp = await theirClient.mutate({mutation: schema.createDirectChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createDirectChat']['chatId']).toBe(chatId)
  expect(resp['data']['createDirectChat']['messageCount']).toBe(1)
  expect(resp['data']['createDirectChat']['messages']['items']).toHaveLength(1)
  expect(resp['data']['createDirectChat']['messages']['items'][0]['messageId']).toBe(messageId1)
  expect(resp['data']['createDirectChat']['messages']['items'][0]['text']).toBe(text)
  expect(resp['data']['createDirectChat']['messages']['items'][0]['textTaggedUsers']).toHaveLength(2)

  // we add a message with one tag
  text = `hi @${theirUsername}!`
  variables = {chatId, messageId: messageId2, text}
  resp = await ourClient.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId2)
  expect(resp['data']['addChatMessage']['text']).toBe(text)
  expect(resp['data']['addChatMessage']['textTaggedUsers']).toHaveLength(1)
  expect(resp['data']['addChatMessage']['textTaggedUsers'][0]['tag']).toBe(`@${theirUsername}`)
  expect(resp['data']['addChatMessage']['textTaggedUsers'][0]['user']['userId']).toBe(theirUserId)

  // we add a message with no tags
  text = 'not tagging anyone here'
  variables = {chatId, messageId: messageId3, text}
  resp = await ourClient.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId3)
  expect(resp['data']['addChatMessage']['text']).toBe(text)
  expect(resp['data']['addChatMessage']['textTaggedUsers']).toHaveLength(0)

  // check the chat, make sure the tags all look as expected
  resp = await theirClient.query({query: schema.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['chat']['messageCount']).toBe(3)
  expect(resp['data']['chat']['messages']['items']).toHaveLength(3)
  expect(resp['data']['chat']['messages']['items'][0]['messageId']).toBe(messageId1)
  expect(resp['data']['chat']['messages']['items'][1]['messageId']).toBe(messageId2)
  expect(resp['data']['chat']['messages']['items'][2]['messageId']).toBe(messageId3)
  expect(resp['data']['chat']['messages']['items'][0]['textTaggedUsers']).toHaveLength(2)
  expect(resp['data']['chat']['messages']['items'][1]['textTaggedUsers']).toHaveLength(1)
  expect(resp['data']['chat']['messages']['items'][1]['textTaggedUsers'][0]['tag']).toBe(`@${theirUsername}`)
  expect(resp['data']['chat']['messages']['items'][1]['textTaggedUsers'][0]['user']['userId']).toBe(theirUserId)
  expect(resp['data']['chat']['messages']['items'][2]['textTaggedUsers']).toHaveLength(0)
})
