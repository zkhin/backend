import dayjs from 'dayjs'
import {v4 as uuidv4} from 'uuid'

import {cognito, eventually} from '../../utils'
import {mutations, queries} from '../../schema'

const loginCache = new cognito.AppSyncLoginCache()

let anonClient, anonUserId
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

test('Create a direct chat', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()
  const {client: randoClient} = await loginCache.getCleanLogin()

  // check we have no direct chat between us
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.directChat).toBeNull()
    expect(data.self.chatCount).toBe(0)
    expect(data.self.chats.items).toHaveLength(0)
  })

  await theirClient.query({query: queries.user, variables: {userId: ourUserId}}).then(({data}) => {
    expect(data.user.directChat).toBeNull()
    expect(data.user.chatCount).toBeNull()
    expect(data.user.chats).toBeNull()
  })

  await ourClient.query({query: queries.user, variables: {userId: theirUserId}}).then(({data}) => {
    expect(data.user.directChat).toBeNull()
    expect(data.user.chatCount).toBeNull()
    expect(data.user.chats).toBeNull()
  })

  // we open up a direct chat with them
  const [chatId, messageId] = [uuidv4(), uuidv4()]
  const messageText = 'lore ipsum'
  const before = dayjs()
  await ourClient
    .mutate({
      mutation: mutations.createDirectChat,
      variables: {userId: theirUserId, chatId, messageId, messageText},
    })
    .then(({data}) => expect(data.createDirectChat.chatId).toBe(chatId))
  const after = dayjs()

  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId, chatType: 'DIRECT', name: null}})
    expect(dayjs(data.chat.createdAt) - before).toBeGreaterThan(0)
    expect(dayjs(data.chat.createdAt) - after).toBeLessThan(0)
    expect(dayjs(data.chat.createdAt) - dayjs(data.chat.lastMessageActivityAt)).toBeLessThan(0)
    expect(data.chat.usersCount).toBe(2)
    expect(data.chat.users.items.map((u) => u.userId).sort()).toEqual([ourUserId, theirUserId].sort())
    expect(data.chat.messages.items).toHaveLength(1)
    expect(data.chat.messages.items[0].messageId).toBe(messageId)
    expect(data.chat.messages.items[0].text).toBe(messageText)
    expect(data.chat.messages.items[0].textTaggedUsers).toEqual([])
    expect(dayjs(data.chat.messages.items[0].createdAt) - dayjs(data.chat.createdAt)).toBeGreaterThan(0)
    expect(data.chat.messages.items[0].lastEditedAt).toBeNull()
    expect(data.chat.messages.items[0].chat.chatId).toBe(chatId)
    expect(data.chat.messages.items[0].author.userId).toBe(ourUserId)
    expect(data.chat.messages.items[0].viewedStatus).toBe('VIEWED')
  })

  // check we can see that direct chat when looking at their profile
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.user, variables: {userId: theirUserId}})
    expect(data.user.directChat.chatId).toBe(chatId)
    expect(data.user.chatCount).toBeNull()
    expect(data.user.chats).toBeNull()
  })

  // check they can see that direct chat when looking at our profile
  await theirClient.query({query: queries.user, variables: {userId: ourUserId}}).then(({data}) => {
    expect(data.user.directChat.chatId).toBe(chatId)
    expect(data.user.chatCount).toBeNull()
    expect(data.user.chats).toBeNull()
  })

  // check we see the chat in our list of chats
  await ourClient.query({query: queries.user, variables: {userId: ourUserId}}).then(({data}) => {
    expect(data.user.directChat).toBeNull()
    expect(data.user.chatCount).toBe(1)
    expect(data.user.chats.items).toHaveLength(1)
    expect(data.user.chats.items[0].chatId).toBe(chatId)
  })

  // check they see the chat in their list of chats
  await theirClient.query({query: queries.user, variables: {userId: theirUserId}}).then(({data}) => {
    expect(data.user.directChat).toBeNull()
    expect(data.user.chatCount).toBe(1)
    expect(data.user.chats.items).toHaveLength(1)
    expect(data.user.chats.items[0].chatId).toBe(chatId)
  })

  // check they can both see the chat directly
  await theirClient
    .query({query: queries.chat, variables: {chatId}})
    .then(({data}) => expect(data).toMatchObject({chat: {chatId}}))

  // check that another rando can't see either the chat either by looking at either of us or direct access
  await randoClient.query({query: queries.user, variables: {userId: ourUserId}}).then(({data}) => {
    expect(data.user.directChat).toBeNull()
    expect(data.user.chatCount).toBeNull()
    expect(data.user.chats).toBeNull()
  })

  await randoClient.query({query: queries.user, variables: {userId: theirUserId}}).then(({data}) => {
    expect(data.user.directChat).toBeNull()
    expect(data.user.chatCount).toBeNull()
    expect(data.user.chats).toBeNull()
  })

  await randoClient
    .query({query: queries.chat, variables: {chatId}})
    .then(({data}) => expect(data.chat).toBeNull())
})

test('Cannot create a direct chat if one already exists', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // they open up a direct chat with us
  const chatId = uuidv4()
  let variables = {userId: ourUserId, chatId, messageId: uuidv4(), messageText: 'lore ipsum'}
  let resp = await theirClient.mutate({mutation: mutations.createDirectChat, variables})
  expect(resp.data.createDirectChat.chatId).toBe(chatId)

  // verify we cannot open up another direct chat with them
  variables = {userId: theirUserId, chatId: uuidv4(), messageId: uuidv4(), messageText: 'lore ipsum'}
  await expect(ourClient.mutate({mutation: mutations.createDirectChat, variables})).rejects.toThrow(
    /ClientError: Chat already exists /,
  )

  // verify they cannot open up another direct chat with us
  variables = {userId: ourUserId, chatId: uuidv4(), messageId: uuidv4(), messageText: 'lore ipsum'}
  await expect(theirClient.mutate({mutation: mutations.createDirectChat, variables})).rejects.toThrow(
    /ClientError: Chat already exists /,
  )
})

test('Cannot create a direct chat if we are disabled', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {userId: theirUserId} = await loginCache.getCleanLogin()

  // we disable ourselves
  let resp = await ourClient.mutate({mutation: mutations.disableUser})
  expect(resp.data.disableUser.userId).toBe(ourUserId)
  expect(resp.data.disableUser.userStatus).toBe('DISABLED')

  // verify we cannot open up another direct chat with them
  let variables = {userId: theirUserId, chatId: uuidv4(), messageId: uuidv4(), messageText: 'lore ipsum'}
  await expect(ourClient.mutate({mutation: mutations.createDirectChat, variables})).rejects.toThrow(
    /ClientError: User .* is not ACTIVE/,
  )
})

test('Anonymous users cannot create direct chats nor be added to one', async () => {
  ;({client: anonClient, userId: anonUserId} = await cognito.getAnonymousAppSyncLogin())
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // check anon user can't create direct chat
  await expect(
    anonClient.mutate({
      mutation: mutations.createDirectChat,
      variables: {userId: theirUserId, chatId: uuidv4(), messageId: uuidv4(), messageText: 'lore ipsum'},
    }),
  ).rejects.toThrow(/ClientError: User .* is not ACTIVE/)

  // check normal user can't create direct chat with anon user
  await expect(
    theirClient.mutate({
      mutation: mutations.createDirectChat,
      variables: {userId: anonUserId, chatId: uuidv4(), messageId: uuidv4(), messageText: 'lore ipsum'},
    }),
  ).rejects.toThrow(/ClientError: .* has non-active status/)
})

test('Cannot open direct chat with self', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()

  const chatId = uuidv4()
  let variables = {userId: ourUserId, chatId, messageId: uuidv4(), messageText: 'lore ipsum'}
  await expect(ourClient.mutate({mutation: mutations.createDirectChat, variables})).rejects.toThrow(
    /ClientError: .* cannot chat with themselves/,
  )
})

test('Create multiple direct chats', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: other1Client} = await loginCache.getCleanLogin()
  const {client: other2Client} = await loginCache.getCleanLogin()

  // check we have no chats
  let resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.chatCount).toBe(0)
  expect(resp.data.self.chats.items).toHaveLength(0)

  // other1 opens up a direct chat with us
  const [chatId1, messageId1] = [uuidv4(), uuidv4()]
  const messageText1 = 'heyya! from other 1'
  let variables = {userId: ourUserId, chatId: chatId1, messageId: messageId1, messageText: messageText1}
  resp = await other1Client.mutate({mutation: mutations.createDirectChat, variables})
  expect(resp.data.createDirectChat.chatId).toBe(chatId1)

  // other2 opens up a direct chat with us
  const [chatId2, messageId2] = [uuidv4(), uuidv4()]
  const messageText2 = 'heyya! from other 2'
  variables = {userId: ourUserId, chatId: chatId2, messageId: messageId2, messageText: messageText2}
  resp = await other2Client.mutate({mutation: mutations.createDirectChat, variables})
  expect(resp.data.createDirectChat.chatId).toBe(chatId2)

  // check we see both chats
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.chatCount).toBe(2)
    expect(data.self.chats.items).toHaveLength(2)
    expect(data.self.chats.items[0].chatId).toBe(chatId2)
    expect(data.self.chats.items[1].chatId).toBe(chatId1)
  })

  // check other1 sees the direct chat with us
  resp = await other1Client.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp.data.user.directChat.chatId).toBe(chatId1)

  // check other2 sees the direct chat with us
  resp = await other2Client.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp.data.user.directChat.chatId).toBe(chatId2)

  // check other1 cannot see other2's chat
  resp = await other1Client.query({query: queries.chat, variables: {chatId: chatId2}})
  expect(resp.data.chat).toBeNull()

  // check other2 cannot see other1's chat
  resp = await other2Client.query({query: queries.chat, variables: {chatId: chatId1}})
  expect(resp.data.chat).toBeNull()
})
