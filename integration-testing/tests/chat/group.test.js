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


test('Create and edit a group chat', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [other1Client, other1UserId] = await loginCache.getCleanLogin()
  const [other2Client, other2UserId] = await loginCache.getCleanLogin()

  // we create a group chat with all of us in it, check details are correct
  const [chatId, messageId1] = [uuidv4(), uuidv4()]
  let variables = {chatId, name: 'x', userIds: [other1UserId, other2UserId], messageId: messageId1, messageText: 'm'}
  let before = moment().toISOString()
  let resp = await ourClient.mutate({mutation: schema.createGroupChat, variables})
  let after = moment().toISOString()
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createGroupChat']['chatId']).toBe(chatId)
  expect(resp['data']['createGroupChat']['chatType']).toBe('GROUP')
  expect(resp['data']['createGroupChat']['name']).toBe('x')
  expect(before <= resp['data']['createGroupChat']['createdAt']).toBe(true)
  expect(after >= resp['data']['createGroupChat']['createdAt']).toBe(true)
  expect(resp['data']['createGroupChat']['createdAt']).toBe(resp['data']['createGroupChat']['lastMessageActivityAt'])
  expect(resp['data']['createGroupChat']['userCount']).toBe(3)
  expect(resp['data']['createGroupChat']['users']['items'].map(u => u['userId']).sort())
    .toEqual([ourUserId, other1UserId, other2UserId].sort())
  expect(resp['data']['createGroupChat']['messageCount']).toBe(1)
  expect(resp['data']['createGroupChat']['messages']['items']).toHaveLength(1)
  expect(resp['data']['createGroupChat']['messages']['items'][0]['messageId']).toBe(messageId1)
  expect(resp['data']['createGroupChat']['messages']['items'][0]['text']).toBe('m')

  // check we have the chat
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['userId']).toBe(ourUserId)
  expect(resp['data']['self']['chatCount']).toBe(1)
  expect(resp['data']['self']['chats']['items']).toHaveLength(1)
  expect(resp['data']['self']['chats']['items'][0]['chatId']).toBe(chatId)

  // check other1 has the chat
  resp = await other1Client.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['userId']).toBe(other1UserId)
  expect(resp['data']['self']['chatCount']).toBe(1)
  expect(resp['data']['self']['chats']['items']).toHaveLength(1)
  expect(resp['data']['self']['chats']['items'][0]['chatId']).toBe(chatId)

  // we add a message
  const messageId2 = uuidv4()
  variables = {chatId, messageId: messageId2, text: 'm2'}
  resp = await ourClient.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId2)

  // other1 adds a message
  const messageId3 = uuidv4()
  variables = {chatId, messageId: messageId3, text: 'm3'}
  resp = await other1Client.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId3)

  // check other2 sees both those messages
  resp = await other2Client.query({query: schema.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['chat']['messageCount']).toBe(3)
  expect(resp['data']['chat']['messages']['items']).toHaveLength(3)
  expect(resp['data']['chat']['messages']['items'][0]['messageId']).toBe(messageId1)
  expect(resp['data']['chat']['messages']['items'][1]['messageId']).toBe(messageId2)
  expect(resp['data']['chat']['messages']['items'][2]['messageId']).toBe(messageId3)

  // other2 edits the name of the group chat
  variables = {chatId, name: 'new name'}
  resp = await other2Client.mutate({mutation: schema.editGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editGroupChat']['chatId']).toBe(chatId)
  expect(resp['data']['editGroupChat']['name']).toBe('new name')

  // check we see the updated name and the messages
  resp = await ourClient.query({query: schema.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['chat']['name']).toBe('new name')
  expect(resp['data']['chat']['messageCount']).toBe(3)
  expect(resp['data']['chat']['messages']['items']).toHaveLength(3)
  expect(resp['data']['chat']['messages']['items'][0]['messageId']).toBe(messageId1)
  expect(resp['data']['chat']['messages']['items'][1]['messageId']).toBe(messageId2)
  expect(resp['data']['chat']['messages']['items'][2]['messageId']).toBe(messageId3)

  // we delete the name of the group chat
  variables = {chatId, name: ''}
  resp = await other2Client.mutate({mutation: schema.editGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editGroupChat']['chatId']).toBe(chatId)
  expect(resp['data']['editGroupChat']['name']).toBeNull()

  // check other1 sees the updated name
  resp = await other1Client.query({query: schema.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['chat']['name']).toBeNull()
})


test('Creating a group chat with our userId in the listed userIds has no affect', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [, theirUserId] = await loginCache.getCleanLogin()

  // we create a group chat with the two of us in it, and we uncessarily add our user Id to the userIds
  const [chatId, messageId] = [uuidv4(), uuidv4()]
  let variables = {chatId, userIds: [ourUserId, theirUserId], messageId, messageText: 'm1'}
  let resp = await ourClient.mutate({mutation: schema.createGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createGroupChat']['chatId']).toBe(chatId)
  expect(resp['data']['createGroupChat']['name']).toBeNull()
  expect(resp['data']['createGroupChat']['userCount']).toBe(2)
  expect(resp['data']['createGroupChat']['users']['items'].map(u => u['userId']).sort())
    .toEqual([ourUserId, theirUserId].sort())
})


test('Create a group chat with just us and without a name, add people to it and leave from it', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()
  const [otherClient, otherUserId] = await loginCache.getCleanLogin()

  // we create a group chat with no name and just us in it
  const [chatId, messageId1] = [uuidv4(), uuidv4()]
  let variables = {chatId, userIds: [], messageId: messageId1, messageText: 'm1'}
  let resp = await ourClient.mutate({mutation: schema.createGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createGroupChat']['chatId']).toBe(chatId)
  expect(resp['data']['createGroupChat']['name']).toBeNull()
  expect(resp['data']['createGroupChat']['userCount']).toBe(1)
  expect(resp['data']['createGroupChat']['users']['items']).toHaveLength(1)
  expect(resp['data']['createGroupChat']['users']['items'][0]['userId']).toBe(ourUserId)

  // check they can't access the chat
  resp = await theirClient.query({query: schema.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']).toBeNull()

  // we add them and other to the chat
  variables = {chatId, userIds: [theirUserId, otherUserId]}
  resp = await ourClient.mutate({mutation: schema.addToGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addToGroupChat']['chatId']).toBe(chatId)
  expect(resp['data']['addToGroupChat']['userCount']).toBe(3)
  expect(resp['data']['addToGroupChat']['users']['items'].map(u => u['userId']).sort())
    .toEqual([ourUserId, theirUserId, otherUserId].sort())

  // check they have the chat now
  resp = await theirClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['userId']).toBe(theirUserId)
  expect(resp['data']['self']['chatCount']).toBe(1)
  expect(resp['data']['self']['chats']['items']).toHaveLength(1)
  expect(resp['data']['self']['chats']['items'][0]['chatId']).toBe(chatId)

  // check other can directly access the chat
  resp = await otherClient.query({query: schema.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)

  // they add a message to the chat
  const messageId2 = uuidv4()
  variables = {chatId, messageId: messageId2, text: 'lore'}
  resp = await theirClient.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId2)

  // they leave the chat
  resp = await theirClient.mutate({mutation: schema.leaveGroupChat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['leaveGroupChat']['chatId']).toBe(chatId)
  expect(resp['data']['leaveGroupChat']['userCount']).toBe(2)

  // check we see their message, we don't see them in the chat
  resp = await ourClient.query({query: schema.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['chat']['userCount']).toBe(2)
  expect(resp['data']['chat']['users']['items']).toHaveLength(2)
  expect(resp['data']['chat']['users']['items'].map(u => u['userId']).sort())
    .toEqual([ourUserId, otherUserId].sort())
  expect(resp['data']['chat']['messageCount']).toBe(2)
  expect(resp['data']['chat']['messages']['items']).toHaveLength(2)
  expect(resp['data']['chat']['messages']['items'][0]['messageId']).toBe(messageId1)
  expect(resp['data']['chat']['messages']['items'][1]['messageId']).toBe(messageId2)

  // we leave the chat
  resp = await ourClient.mutate({mutation: schema.leaveGroupChat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['leaveGroupChat']['chatId']).toBe(chatId)
  expect(resp['data']['leaveGroupChat']['userCount']).toBe(1)

  // check we can no longer access the chat
  resp = await ourClient.query({query: schema.chat, variables: {chatId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['chat']).toBeNull()
})


test('Add someone to a group chat that is already there is a no-op', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [, other1UserId] = await loginCache.getCleanLogin()
  const [, other2UserId] = await loginCache.getCleanLogin()

  // we create a group chat with both of us in it
  const chatId = uuidv4()
  let variables = {chatId, userIds: [other1UserId], messageId: uuidv4(), messageText: 'm1'}
  let resp = await ourClient.mutate({mutation: schema.createGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createGroupChat']['chatId']).toBe(chatId)
  expect(resp['data']['createGroupChat']['userCount']).toBe(2)
  expect(resp['data']['createGroupChat']['users']['items'].map(u => u['userId']).sort())
    .toEqual([ourUserId, other1UserId].sort())

  // check adding to them to the chat again does nothing
  variables = {chatId, userIds: [other1UserId]}
  resp = await ourClient.mutate({mutation: schema.addToGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addToGroupChat']['chatId']).toBe(chatId)
  expect(resp['data']['addToGroupChat']['userCount']).toBe(2)
  expect(resp['data']['addToGroupChat']['users']['items'].map(u => u['userId']).sort())
    .toEqual([ourUserId, other1UserId].sort())

  // check adding to them and another user to the chat at the same time adds the other user
  variables = {chatId, userIds: [other1UserId, other2UserId]}
  resp = await ourClient.mutate({mutation: schema.addToGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addToGroupChat']['chatId']).toBe(chatId)
  expect(resp['data']['addToGroupChat']['userCount']).toBe(3)
  expect(resp['data']['addToGroupChat']['users']['items'].map(u => u['userId']).sort())
    .toEqual([ourUserId, other1UserId, other2UserId].sort())
})


test('Cannot add someone to a chat that DNE, that we are not in or that is a a direct chat', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [other1Client, other1UserId] = await loginCache.getCleanLogin()
  const [, other2UserId] = await loginCache.getCleanLogin()

  // check we can't add other1 to a chat that DNE
  let variables = {chatId: uuidv4(), userIds: [other1UserId]}
  await expect(ourClient.mutate({mutation: schema.addToGroupChat, variables})).rejects.toThrow('ClientError')

  // other1 creates a group chat with only themselves in it
  const chatId1 = uuidv4()
  variables = {chatId: chatId1, userIds: [], messageId: uuidv4(), messageText: 'm'}
  let resp = await other1Client.mutate({mutation: schema.createGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createGroupChat']['chatId']).toBe(chatId1)
  expect(resp['data']['createGroupChat']['chatType']).toBe('GROUP')

  // check we cannot add other2 to that group chat
  variables = {chatId: chatId1, userIds: [other2UserId]}
  await expect(ourClient.mutate({mutation: schema.addToGroupChat, variables})).rejects.toThrow('ClientError')

  // we create a direct chat with other2
  const chatId2 = uuidv4()
  variables = {userId: other2UserId, chatId: chatId2, messageId: uuidv4(), messageText: 'lore ipsum'}
  resp = await ourClient.mutate({mutation: schema.createDirectChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createDirectChat']['chatId']).toBe(chatId2)
  expect(resp['data']['createDirectChat']['chatType']).toBe('DIRECT')

  // check we cannot add other1 to that direct chat
  variables = {chatId: chatId2, userIds: [other1UserId]}
  await expect(ourClient.mutate({mutation: schema.addToGroupChat, variables})).rejects.toThrow('ClientError')
})


test('Cannot leave a chat that DNE, that we are not in, or that is a direct chat', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // check we cannot leave a chat that DNE
  let variables = {chatId: uuidv4()}
  await expect(ourClient.mutate({mutation: schema.leaveGroupChat, variables})).rejects.toThrow('ClientError')

  // they create a group chat with only themselves in it
  const chatId1 = uuidv4()
  variables = {chatId: chatId1, userIds: [], messageId: uuidv4(), messageText: 'm'}
  let resp = await theirClient.mutate({mutation: schema.createGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createGroupChat']['chatId']).toBe(chatId1)
  expect(resp['data']['createGroupChat']['chatType']).toBe('GROUP')

  // check we cannot leave from that group chat we are not in
  variables = {chatId: chatId1}
  await expect(ourClient.mutate({mutation: schema.leaveGroupChat, variables})).rejects.toThrow('ClientError')

  // we create a direct chat with them
  const chatId2 = uuidv4()
  variables = {userId: theirUserId, chatId: chatId2, messageId: uuidv4(), messageText: 'lore ipsum'}
  resp = await ourClient.mutate({mutation: schema.createDirectChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createDirectChat']['chatId']).toBe(chatId2)
  expect(resp['data']['createDirectChat']['chatType']).toBe('DIRECT')

  // check we cannot leave that direct chat
  variables = {chatId: chatId2}
  await expect(ourClient.mutate({mutation: schema.leaveGroupChat, variables})).rejects.toThrow('ClientError')
})


test('Cannnot edit name of chat that DNE, that we are not in, or that is a direct chat', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // check we cannot edit a chat that DNE
  let variables = {chatId: uuidv4(), name: 'new name'}
  await expect(ourClient.mutate({mutation: schema.leaveGroupChat, variables})).rejects.toThrow('ClientError')

  // they create a group chat with only themselves in it
  const chatId1 = uuidv4()
  variables = {chatId: chatId1, userIds: [], messageId: uuidv4(), messageText: 'm'}
  let resp = await theirClient.mutate({mutation: schema.createGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createGroupChat']['chatId']).toBe(chatId1)
  expect(resp['data']['createGroupChat']['chatType']).toBe('GROUP')

  // check we cannot edit the name of their group chat
  variables = {chatId: chatId1, name: 'c name'}
  await expect(ourClient.mutate({mutation: schema.editGroupChat, variables})).rejects.toThrow('ClientError')

  // we create a direct chat with them
  const chatId2 = uuidv4()
  variables = {userId: theirUserId, chatId: chatId2, messageId: uuidv4(), messageText: 'lore ipsum'}
  resp = await ourClient.mutate({mutation: schema.createDirectChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createDirectChat']['chatId']).toBe(chatId2)
  expect(resp['data']['createDirectChat']['chatType']).toBe('DIRECT')

  // check we cannot edit the name of that direct chat
  variables = {chatId: chatId2, name: 'c name'}
  await expect(ourClient.mutate({mutation: schema.leaveGroupChat, variables})).rejects.toThrow('ClientError')
})
