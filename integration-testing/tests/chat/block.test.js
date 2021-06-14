import {v4 as uuidv4} from 'uuid'

import {cognito, eventually, sleep} from '../../utils'
import {mutations, queries} from '../../schema'

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Blocking a user causes our direct chat with them to disappear to both of us', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // they open up a chat with us
  const [chatId, messageId1, text1] = [uuidv4(), uuidv4(), 'hey this is msg 1']
  await theirClient.mutate({
    mutation: mutations.createDirectChat,
    variables: {userId: ourUserId, chatId, messageId: messageId1, messageText: text1},
  })

  // check we can see the chat
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
  })

  // check the chat appears in their list of chats
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.self})
    expect(data.self.chatCount).toBe(1)
    expect(data.self.chats.items).toHaveLength(1)
    expect(data.self.chats.items[0].chatId).toBe(chatId)
  })

  // we block them
  await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: theirUserId}}).then(({data}) => {
    expect(data.blockUser.userId).toBe(theirUserId)
    expect(data.blockUser.blockedStatus).toBe('BLOCKING')
  })

  // check neither of us can directly see the chat anymore
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data.chat).toBeNull()
  })
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.chat, variables: {chatId}})
    expect(data.chat).toBeNull()
  })

  // check neither of us see the chat by looking at each other's profiles
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
    expect(data.user.directChat).toBeNull()
  })
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.user, variables: {userId: theirUserId}})
    expect(data.user.directChat).toBeNull()
  })

  // check niether of us see the chat in our list of chats
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.chatCount).toBe(0)
    expect(data.self.chats.items).toHaveLength(0)
  })
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.self})
    expect(data.self.chatCount).toBe(0)
    expect(data.self.chats.items).toHaveLength(0)
  })
})

test('Cannot open a direct chat with a user that blocks us or that we block', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // we block them
  let resp = await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: theirUserId}})
  expect(resp.data.blockUser.userId).toBe(theirUserId)
  expect(resp.data.blockUser.blockedStatus).toBe('BLOCKING')

  // check they cannot open up a direct chat with us
  const chatVars = {chatId: uuidv4(), messageId: uuidv4(), messageText: 'lore ipsum'}
  let variables = {userId: ourUserId, ...chatVars}
  await expect(theirClient.mutate({mutation: mutations.createDirectChat, variables})).rejects.toThrow(
    /ClientError: .* has been blocked by /,
  )

  // check we cannot open up a direct chat with them
  variables = {userId: theirUserId, ...chatVars}
  await expect(ourClient.mutate({mutation: mutations.createDirectChat, variables})).rejects.toThrow(
    /ClientError: .* has blocked /,
  )
})

test('Blocking a user we are in a group chat with', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // we create a group chat with them
  const [chatId, messageId1] = [uuidv4(), uuidv4()]
  let variables = {chatId, userIds: [theirUserId], messageId: messageId1, messageText: 'm1'}
  let resp = await ourClient.mutate({mutation: mutations.createGroupChat, variables})
  expect(resp.data.createGroupChat.chatId).toBe(chatId)

  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
  })

  // they add a message to the chat
  const messageId2 = uuidv4()
  variables = {chatId, messageId: messageId2, text: 'lore'}
  resp = await theirClient.mutate({mutation: mutations.addChatMessage, variables})
  expect(resp.data.addChatMessage.messageId).toBe(messageId2)

  // they block us
  resp = await theirClient.mutate({mutation: mutations.blockUser, variables: {userId: ourUserId}})
  expect(resp.data.blockUser.userId).toBe(ourUserId)
  expect(resp.data.blockUser.blockedStatus).toBe('BLOCKING')

  // check we still see the chat, but don't see them in it and their messages have an authorUserId but no author
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.usersCount).toBe(2)
    expect(data.chat.users.items).toHaveLength(1)
    expect(data.chat.users.items[0].userId).toBe(ourUserId)
    expect(data.chat.messagesCount).toBe(5)
    expect(data.chat.messages.items).toHaveLength(5)
    expect(data.chat.messages.items[3].messageId).toBe(messageId1)
    expect(data.chat.messages.items[4].messageId).toBe(messageId2)
    expect(data.chat.messages.items[4].authorUserId).toBe(theirUserId)
    expect(data.chat.messages.items[4].author).toBeNull()
  })

  // check they still see the chat, and still see us and our messages (for now - would be better to block those)
  await theirClient.query({query: queries.chat, variables: {chatId}}).then(({data}) => {
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.usersCount).toBe(2)
    expect(data.chat.users.items.map((u) => u.userId).sort()).toEqual([ourUserId, theirUserId].sort())
    expect(data.chat.messagesCount).toBe(5)
    expect(data.chat.messages.items).toHaveLength(5)
    expect(data.chat.messages.items[3].messageId).toBe(messageId1)
    expect(data.chat.messages.items[3].authorUserId).toBe(ourUserId)
    expect(data.chat.messages.items[3].author.userId).toBe(ourUserId)
    expect(data.chat.messages.items[4].messageId).toBe(messageId2)
  })
})

test('Creating a group chat with users with have a blocking relationship skips them', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()
  const {userId: otherUserId} = await loginCache.getCleanLogin()

  // they block us
  await theirClient.mutate({mutation: mutations.blockUser, variables: {userId: ourUserId}}).then(({data}) => {
    expect(data.blockUser.userId).toBe(ourUserId)
    expect(data.blockUser.blockedStatus).toBe('BLOCKING')
  })

  // we create a group chat with all three of us, skips them
  const chatId1 = uuidv4()
  await ourClient.mutate({
    mutation: mutations.createGroupChat,
    variables: {chatId: chatId1, userIds: [theirUserId, otherUserId], messageId: uuidv4(), messageText: 'm1'},
  })
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId: chatId1}})
    expect(data).toMatchObject({chat: {chatId: chatId1}})
    expect(data.chat.usersCount).toBe(2)
    expect(data.chat.users.items.map((u) => u.userId).sort()).toEqual([ourUserId, otherUserId].sort())
  })

  // check they cannot see that chat
  await theirClient
    .query({query: queries.chat, variables: {chatId: chatId1}})
    .then(({data}) => expect(data.chat).toBeNull())

  // they create a group chat with just us and them
  const chatId2 = uuidv4()
  await theirClient.mutate({
    mutation: mutations.createGroupChat,
    variables: {chatId: chatId2, userIds: [ourUserId], messageId: uuidv4(), messageText: 'm1'},
  })
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.chat, variables: {chatId: chatId2}})
    expect(data).toMatchObject({chat: {chatId: chatId2}})
    expect(data.chat.usersCount).toBe(1)
    expect(data.chat.users.items.map((u) => u.userId)).toEqual([theirUserId])
  })

  // check we cannot see the chat
  await ourClient
    .query({query: queries.chat, variables: {chatId: chatId2}})
    .then(({data}) => expect(data.chat).toBeNull())
})

test('Adding somebody we have a blocking relationship with to a group chat skips them', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: other1Client, userId: other1UserId} = await loginCache.getCleanLogin()
  const {userId: other2UserId} = await loginCache.getCleanLogin()

  // other1 blocks us
  await other1Client.mutate({mutation: mutations.blockUser, variables: {userId: ourUserId}}).then(({data}) => {
    expect(data.blockUser.userId).toBe(ourUserId)
    expect(data.blockUser.blockedStatus).toBe('BLOCKING')
  })

  // we block other2
  await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: other2UserId}}).then(({data}) => {
    expect(data.blockUser.userId).toBe(other2UserId)
    expect(data.blockUser.blockedStatus).toBe('BLOCKING')
  })

  // we create a group chat with just us in it
  const chatId = uuidv4()
  await ourClient.mutate({
    mutation: mutations.createGroupChat,
    variables: {chatId, userIds: [], messageId: uuidv4(), messageText: 'm1'},
  })
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.usersCount).toBe(1)
    expect(data.chat.users.items.map((u) => u.userId)).toEqual([ourUserId])
  })

  // try to add other1, other2 to the chat
  await ourClient.mutate({mutation: mutations.addToGroupChat, variables: {chatId, userIds: [other1UserId]}})
  await ourClient.mutate({mutation: mutations.addToGroupChat, variables: {chatId, userIds: [other2UserId]}})

  // check the chat still shows just us in it
  await sleep()
  await ourClient.query({query: queries.chat, variables: {chatId}}).then(({data}) => {
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.usersCount).toBe(1)
    expect(data.chat.users.items.map((u) => u.userId)).toEqual([ourUserId])
  })
})

test('A group chat with two users that have a blocking relationship between them', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: other1Client, userId: other1UserId} = await loginCache.getCleanLogin()
  const {client: other2Client, userId: other2UserId} = await loginCache.getCleanLogin()

  // other1 blocks other2
  await other1Client.mutate({mutation: mutations.blockUser, variables: {userId: other2UserId}}).then(({data}) => {
    expect(data.blockUser.userId).toBe(other2UserId)
    expect(data.blockUser.blockedStatus).toBe('BLOCKING')
  })

  // we create a group chat with all three of us in it
  const chatId = uuidv4()
  await ourClient.mutate({
    mutation: mutations.createGroupChat,
    variables: {chatId, userIds: [other1UserId, other2UserId], messageId: uuidv4(), messageText: 'm1'},
  })
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.usersCount).toBe(3)
    expect(data.chat.users.items.map((u) => u.userId).sort()).toEqual(
      [ourUserId, other1UserId, other2UserId].sort(),
    )
  })

  // check other1 does see other2 in it (for now - maybe we should change this?)
  await eventually(async () => {
    const {data} = await other1Client.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.usersCount).toBe(3)
    expect(data.chat.users.items.map((u) => u.userId).sort()).toEqual(
      [ourUserId, other1UserId, other2UserId].sort(),
    )
  })

  // check other2 doesn't see other1 in it
  await eventually(async () => {
    const {data} = await other2Client.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.usersCount).toBe(3)
    expect(data.chat.users.items.map((u) => u.userId).sort()).toEqual([ourUserId, other2UserId].sort())
  })
})
