/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const { mutations, queries } = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
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
  let resp = await theirClient.mutate({mutation: mutations.createDirectChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createDirectChat']['chatId']).toBe(chatId)

  // check we can see the chat
  resp = await ourClient.query({query: queries.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)

  // check the chat appears in their list of chats
  resp = await theirClient.query({query: queries.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['chatCount']).toBe(1)
  expect(resp['data']['self']['chats']['items']).toHaveLength(1)
  expect(resp['data']['self']['chats']['items'][0]['chatId']).toBe(chatId)

  // we block them
  resp = await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(theirUserId)
  expect(resp['data']['blockUser']['blockedStatus']).toBe('BLOCKING')

  // check neither of us can directly see the chat anymore
  resp = await ourClient.query({query: queries.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']).toBeNull()

  resp = await theirClient.query({query: queries.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']).toBeNull()

  // check neither of us see the chat by looking at each other's profiles
  resp = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['directChat']).toBeNull()

  resp = await ourClient.query({query: queries.user, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['directChat']).toBeNull()

  // check niether of us see the chat in our list of chats
  resp = await ourClient.query({query: queries.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['chatCount']).toBe(0)
  expect(resp['data']['self']['chats']['items']).toHaveLength(0)

  resp = await theirClient.query({query: queries.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['chatCount']).toBe(0)
  expect(resp['data']['self']['chats']['items']).toHaveLength(0)
})


test('Cannot open a direct chat with a user that blocks us or that we block', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we block them
  let resp = await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(theirUserId)
  expect(resp['data']['blockUser']['blockedStatus']).toBe('BLOCKING')

  // check they cannot open up a direct chat with us
  const chatVars = {chatId: uuidv4(), messageId: uuidv4(), messageText: 'lore ipsum'}
  let variables = {userId: ourUserId, ...chatVars}
  await expect(theirClient.mutate({mutation: mutations.createDirectChat, variables})).rejects.toThrow('ClientError')

  // check we cannot open up a direct chat with them
  variables = {userId: theirUserId, ...chatVars}
  await expect(ourClient.mutate({mutation: mutations.createDirectChat, variables})).rejects.toThrow('ClientError')
})


test('Blocking a user we are in a group chat with', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we create a group chat with them
  const [chatId, messageId1] = [uuidv4(), uuidv4()]
  let variables = {chatId, userIds: [theirUserId], messageId: messageId1, messageText: 'm1'}
  let resp = await ourClient.mutate({mutation: mutations.createGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createGroupChat']['chatId']).toBe(chatId)

  // they add a message to the chat
  const messageId2 = uuidv4()
  variables = {chatId, messageId: messageId2, text: 'lore'}
  resp = await theirClient.mutate({mutation: mutations.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId2)

  // they block us
  resp = await theirClient.mutate({mutation: mutations.blockUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(ourUserId)
  expect(resp['data']['blockUser']['blockedStatus']).toBe('BLOCKING')

  // check we still see the chat, but don't see them in it and their messages have an authorUserId but no author
  resp = await ourClient.query({query: queries.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['chat']['userCount']).toBe(2)
  expect(resp['data']['chat']['users']['items']).toHaveLength(1)
  expect(resp['data']['chat']['users']['items'][0]['userId']).toBe(ourUserId)
  expect(resp['data']['chat']['messageCount']).toBe(4)
  expect(resp['data']['chat']['messages']['items']).toHaveLength(4)
  expect(resp['data']['chat']['messages']['items'][2]['messageId']).toBe(messageId1)
  expect(resp['data']['chat']['messages']['items'][3]['messageId']).toBe(messageId2)
  expect(resp['data']['chat']['messages']['items'][3]['authorUserId']).toBe(theirUserId)
  expect(resp['data']['chat']['messages']['items'][3]['author']).toBeNull()

  // check they still see the chat, and still see us and our messages (for now - would be better to block those)
  resp = await theirClient.query({query: queries.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['chat']['userCount']).toBe(2)
  expect(resp['data']['chat']['users']['items'].map(u => u['userId']).sort())
    .toEqual([ourUserId, theirUserId].sort())
  expect(resp['data']['chat']['messageCount']).toBe(4)
  expect(resp['data']['chat']['messages']['items']).toHaveLength(4)
  expect(resp['data']['chat']['messages']['items'][2]['messageId']).toBe(messageId1)
  expect(resp['data']['chat']['messages']['items'][2]['authorUserId']).toBe(ourUserId)
  expect(resp['data']['chat']['messages']['items'][2]['author']['userId']).toBe(ourUserId)
  expect(resp['data']['chat']['messages']['items'][3]['messageId']).toBe(messageId2)
})


test('Creating a group chat with users with have a blocking relationship skips them', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()
  const [, otherUserId] = await loginCache.getCleanLogin()

  // they block us
  let resp = await theirClient.mutate({mutation: mutations.blockUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(ourUserId)
  expect(resp['data']['blockUser']['blockedStatus']).toBe('BLOCKING')

  // we create a group chat with all three of us, skips them
  const chatId1 = uuidv4()
  let variables = {chatId: chatId1, userIds: [theirUserId, otherUserId], messageId: uuidv4(), messageText: 'm1'}
  resp = await ourClient.mutate({mutation: mutations.createGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createGroupChat']['chatId']).toBe(chatId1)
  expect(resp['data']['createGroupChat']['userCount']).toBe(2)
  expect(resp['data']['createGroupChat']['users']['items'].map(u => u['userId']).sort())
    .toEqual([ourUserId, otherUserId].sort())

  // check they cannot see that chat
  resp = await theirClient.query({query: queries.chat, variables: {chatId: chatId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']).toBeNull()

  // they create a group chat with just us and them
  const chatId2 = uuidv4()
  variables = {chatId: chatId2, userIds: [ourUserId], messageId: uuidv4(), messageText: 'm1'}
  resp = await theirClient.mutate({mutation: mutations.createGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createGroupChat']['chatId']).toBe(chatId2)
  expect(resp['data']['createGroupChat']['userCount']).toBe(1)
  expect(resp['data']['createGroupChat']['users']['items'].map(u => u['userId'])).toEqual([theirUserId])

  // check we cannot see the chat
  resp = await ourClient.query({query: queries.chat, variables: {chatId: chatId2}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']).toBeNull()
})


test('Adding somebody we have a blocking relationship with to a group chat skips them', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [other1Client, other1UserId] = await loginCache.getCleanLogin()
  const [, other2UserId] = await loginCache.getCleanLogin()

  // other1 blocks us
  let resp = await other1Client.mutate({mutation: mutations.blockUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(ourUserId)
  expect(resp['data']['blockUser']['blockedStatus']).toBe('BLOCKING')

  // we block other2
  resp = await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: other2UserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(other2UserId)
  expect(resp['data']['blockUser']['blockedStatus']).toBe('BLOCKING')

  // we create a group chat with just us in it
  const chatId = uuidv4()
  let variables = {chatId, userIds: [], messageId: uuidv4(), messageText: 'm1'}
  resp = await ourClient.mutate({mutation: mutations.createGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createGroupChat']['chatId']).toBe(chatId)
  expect(resp['data']['createGroupChat']['userCount']).toBe(1)
  expect(resp['data']['createGroupChat']['users']['items'].map(u => u['userId'])).toEqual([ourUserId])

  // check if we try to add other1 to the chat, it skips them
  variables = {chatId, userIds: [other1UserId]}
  resp = await ourClient.mutate({mutation: mutations.addToGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addToGroupChat']['chatId']).toBe(chatId)
  expect(resp['data']['addToGroupChat']['userCount']).toBe(1)
  expect(resp['data']['addToGroupChat']['users']['items'].map(u => u['userId'])).toEqual([ourUserId])

  // check we cannot other2 to it
  variables = {chatId, userIds: [other2UserId]}
  resp = await ourClient.mutate({mutation: mutations.addToGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addToGroupChat']['chatId']).toBe(chatId)
  expect(resp['data']['addToGroupChat']['userCount']).toBe(1)
  expect(resp['data']['addToGroupChat']['users']['items'].map(u => u['userId'])).toEqual([ourUserId])

  // check the chat still shows just us in it
  resp = await ourClient.query({query: queries.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['chat']['userCount']).toBe(1)
  expect(resp['data']['chat']['users']['items'].map(u => u['userId'])).toEqual([ourUserId])
})


test('Test create a group chat with two users that have a blocking relationship between them', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [other1Client, other1UserId] = await loginCache.getCleanLogin()
  const [other2Client, other2UserId] = await loginCache.getCleanLogin()

  // other1 blocks other2
  let resp = await other1Client.mutate({mutation: mutations.blockUser, variables: {userId: other2UserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(other2UserId)
  expect(resp['data']['blockUser']['blockedStatus']).toBe('BLOCKING')

  // we create a group chat with all three of us in it
  const chatId = uuidv4()
  let variables = {chatId, userIds: [other1UserId, other2UserId], messageId: uuidv4(), messageText: 'm1'}
  resp = await ourClient.mutate({mutation: mutations.createGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createGroupChat']['chatId']).toBe(chatId)
  expect(resp['data']['createGroupChat']['userCount']).toBe(3)
  expect(resp['data']['createGroupChat']['users']['items'].map(u => u['userId']).sort())
    .toEqual([ourUserId, other1UserId, other2UserId].sort())

  // check other1 does see other2 in it (for now - maybe we should change this?)
  resp = await other1Client.query({query: queries.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['chat']['userCount']).toBe(3)
  expect(resp['data']['chat']['users']['items'].map(u => u['userId']).sort())
    .toEqual([ourUserId, other1UserId, other2UserId].sort())

  // check other2 doesn't see other1 in it
  resp = await other2Client.query({query: queries.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['chat']['userCount']).toBe(3)
  expect(resp['data']['chat']['users']['items'].map(u => u['userId']).sort())
    .toEqual([ourUserId, other2UserId].sort())

  // check we see everyone in it
  resp = await ourClient.query({query: queries.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['chat']['userCount']).toBe(3)
  expect(resp['data']['chat']['users']['items'].map(u => u['userId']).sort())
    .toEqual([ourUserId, other1UserId, other2UserId].sort())
})
