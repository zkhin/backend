import {v4 as uuidv4} from 'uuid'

import {cognito, eventually, sleep} from '../../utils'
import {mutations, queries} from '../../schema'

const loginCache = new cognito.AppSyncLoginCache()

let anonClient
// https://github.com/real-social-media/bad_words/blob/master/bucket/bad_words.json
const badWord = 'uoiFZP8bjS'

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

  await ourClient.mutate({mutation: mutations.createDirectChat, variables})
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.messages.items).toHaveLength(1)
    expect(data.chat.messages.items[0].messageId).toBe(messageId)
    expect(data.chat.messages.items[0].text).toBe(messageText)
    expect(data.chat.messages.items[0].chat.chatId).toBe(chatId)
    expect(data.chat.messages.items[0].author.userId).toBe(ourUserId)
    expect(data.chat.messages.items[0].viewedStatus).toBe('VIEWED')
  })

  // check we see the chat in our list of chats
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.user, variables: {userId: ourUserId}})
    expect(data.user.directChat).toBeNull()
    expect(data.user.chatCount).toBe(1)
    expect(data.user.chats.items).toHaveLength(1)
    expect(data.user.chats.items[0].chatId).toBe(chatId)
  })

  // check they see the chat in their list of chats
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.user, variables: {userId: theirUserId}})
    expect(data.user.directChat).toBeNull()
    expect(data.user.chatCount).toBe(1)
    expect(data.user.chats.items).toHaveLength(1)
    expect(data.user.chats.items[0].chatId).toBe(chatId)
  })

  // check we can both see the chat directly
  await ourClient.query({query: queries.chat, variables: {chatId}}).then(({data: {chat}}) => {
    expect(chat.chatId).toBe(chatId)
  })

  await theirClient.query({query: queries.chat, variables: {chatId}}).then(({data: {chat}}) => {
    expect(chat.chatId).toBe(chatId)
  })

  // they add chat message with bad word, verify it's removed
  const [messageId2, messageText2] = [uuidv4(), `msg ${badWord}`]
  variables = {chatId, messageId: messageId2, text: messageText2}
  await theirClient
    .mutate({mutation: mutations.addChatMessage, variables})
    .then(({data: {addChatMessage: chatMessage}}) => {
      expect(chatMessage.messageId).toBe(messageId2)
      expect(chatMessage.text).toBe(messageText2)
      expect(chatMessage.chat.chatId).toBe(chatId)
    })

  // verify the bad word chat is removed
  await sleep()
  await ourClient.query({query: queries.user, variables: {userId: ourUserId}}).then(({data: {user}}) => {
    expect(user.chatCount).toBe(1)
    expect(user.chats.items).toHaveLength(1)
    expect(user.chats.items[0].chatId).toBe(chatId)
  })
  await ourClient.query({query: queries.chat, variables: {chatId}}).then(({data: {chat}}) => {
    expect(chat.chatId).toBe(chatId)
    expect(chat.messages.items).toHaveLength(1)
  })

  // edit the message, verify it's removed
  const messageText3 = `msg ${badWord.toUpperCase()}`
  await ourClient
    .mutate({mutation: mutations.editChatMessage, variables: {messageId, text: messageText3}})
    .then(({data: {editChatMessage: chatMessage}}) => {
      expect(chatMessage.messageId).toBe(messageId)
      expect(chatMessage.text).toBe(messageText3)
      expect(chatMessage.chat.chatId).toBe(chatId)
    })

  // verify the bad word chat is removed
  await sleep()
  await ourClient.query({query: queries.user, variables: {userId: ourUserId}}).then(({data: {user}}) => {
    expect(user.chatCount).toBe(1)
    expect(user.chats.items).toHaveLength(1)
    expect(user.chats.items[0].chatId).toBe(chatId)
  })
  await ourClient.query({query: queries.chat, variables: {chatId}}).then(({data: {chat}}) => {
    expect(chat.chatId).toBe(chatId)
    expect(chat.message).toBeUndefined()
  })
})

test('Two way follow, skip bad word detection - direct chat', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // we open up a direct chat with them
  const [chatId, messageId] = [uuidv4(), uuidv4()]
  const messageText = 'lore ipsum'
  let variables = {userId: theirUserId, chatId, messageId, messageText}

  await ourClient.mutate({mutation: mutations.createDirectChat, variables})
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.messages.items).toHaveLength(1)
    expect(data.chat.messages.items[0].messageId).toBe(messageId)
    expect(data.chat.messages.items[0].text).toBe(messageText)
    expect(data.chat.messages.items[0].chat.chatId).toBe(chatId)
    expect(data.chat.messages.items[0].author.userId).toBe(ourUserId)
    expect(data.chat.messages.items[0].viewedStatus).toBe('VIEWED')
  })

  // check we see the chat in our list of chats
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.user, variables: {userId: ourUserId}})
    expect(data.user.directChat).toBeNull()
    expect(data.user.chatCount).toBe(1)
    expect(data.user.chats.items).toHaveLength(1)
    expect(data.user.chats.items[0].chatId).toBe(chatId)
  })

  // they follow us
  await theirClient
    .mutate({mutation: mutations.followUser, variables: {userId: ourUserId}})
    .then(({data}) => expect(data.followUser.followedStatus).toBe('FOLLOWING'))

  // we follow them
  await ourClient
    .mutate({mutation: mutations.followUser, variables: {userId: theirUserId}})
    .then(({data}) => expect(data.followUser.followedStatus).toBe('FOLLOWING'))

  // they add chat message with bad word, verify chat message is added
  const [messageId2, messageText2] = [uuidv4(), `msg ${badWord}`]
  variables = {chatId, messageId: messageId2, text: messageText2}
  await theirClient
    .mutate({mutation: mutations.addChatMessage, variables})
    .then(({data: {addChatMessage: chatMessage}}) => {
      expect(chatMessage.messageId).toBe(messageId2)
      expect(chatMessage.text).toBe(messageText2)
      expect(chatMessage.chat.chatId).toBe(chatId)
    })

  // check we see all chat messages
  await sleep()
  await ourClient.query({query: queries.user, variables: {userId: ourUserId}}).then(({data: {user}}) => {
    expect(user.chatCount).toBe(1)
    expect(user.chats.items).toHaveLength(1)
    expect(user.chats.items[0].chatId).toBe(chatId)
  })
  await ourClient.query({query: queries.chat, variables: {chatId}}).then(({data: {chat}}) => {
    expect(chat.chatId).toBe(chatId)
    expect(chat.messages.items).toHaveLength(2)
    expect(chat.messages.items[0].messageId).toBe(messageId)
    expect(chat.messages.items[0].text).toBe(messageText)
    expect(chat.messages.items[0].chat.chatId).toBe(chatId)
    expect(chat.messages.items[1].messageId).toBe(messageId2)
    expect(chat.messages.items[1].text).toBe(messageText2)
    expect(chat.messages.items[1].chat.chatId).toBe(chatId)
  })
})

test('Create a group chat with bad word', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()
  const {client: otherClient, userId: otherUserId} = await loginCache.getCleanLogin()

  const [chatId, messageId1] = [uuidv4(), uuidv4()]
  let variables = {
    chatId,
    name: 'x',
    userIds: [theirUserId, otherUserId],
    messageId: messageId1,
    messageText: 'm',
  }
  await ourClient.mutate({mutation: mutations.createGroupChat, variables})
  const first5MessageIds = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.messages.items).toHaveLength(5)
    expect(data.chat.messages.items[0].text).toContain('created the group')
    expect(data.chat.messages.items[1].text).toContain('added to the group')
    expect(data.chat.messages.items[2].text).toContain('added to the group')
    expect(data.chat.messages.items[3].text).toContain('added to the group')
    expect(data.chat.messages.items[4].messageId).toBe(messageId1)
    return data.chat.messages.items.map((item) => item.messageId)
  })

  // we add a message
  const messageId2 = uuidv4()
  variables = {chatId, messageId: messageId2, text: 'm2'}
  await ourClient
    .mutate({mutation: mutations.addChatMessage, variables})
    .then(({data: {addChatMessage: chatMessage}}) => {
      expect(chatMessage.messageId).toBe(messageId2)
    })

  // they add a message with bad word
  const messageId3 = uuidv4()
  variables = {chatId, messageId: messageId3, text: `m3 ${badWord}`}
  await theirClient
    .mutate({mutation: mutations.addChatMessage, variables})
    .then(({data: {addChatMessage: chatMessage}}) => {
      expect(chatMessage.messageId).toBe(messageId3)
    })

  // verify bad word chat message is removed
  await sleep()
  await otherClient.query({query: queries.chat, variables: {chatId}}).then(({data}) => {
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.messagesCount).toBe(6)
    expect(data.chat.messages.items).toHaveLength(6)
    expect(data.chat.messages.items.slice(0, 5).map((item) => item.messageId)).toEqual(first5MessageIds)
    expect(data.chat.messages.items[5].messageId).toBe(messageId2)
  })
})

test('Create a group chat with bad word - skip if all users follow creator', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()
  const {client: otherClient, userId: otherUserId} = await loginCache.getCleanLogin()

  const [chatId, messageId1] = [uuidv4(), uuidv4()]
  let variables = {
    chatId,
    name: 'x',
    userIds: [theirUserId, otherUserId],
    messageId: messageId1,
    messageText: 'm',
  }
  await ourClient.mutate({mutation: mutations.createGroupChat, variables})
  const first5MessageIds = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.messages.items).toHaveLength(5)
    expect(data.chat.messages.items[0].text).toContain('created the group')
    expect(data.chat.messages.items[1].text).toContain('added to the group')
    expect(data.chat.messages.items[2].text).toContain('added to the group')
    expect(data.chat.messages.items[3].text).toContain('added to the group')
    expect(data.chat.messages.items[4].messageId).toBe(messageId1)
    return data.chat.messages.items.map((item) => item.messageId)
  })

  // we add a message
  const messageId2 = uuidv4()
  variables = {chatId, messageId: messageId2, text: 'm2'}
  await ourClient
    .mutate({mutation: mutations.addChatMessage, variables})
    .then(({data: {addChatMessage: chatMessage}}) => {
      expect(chatMessage.messageId).toBe(messageId2)
    })

  // we and other follow them
  await ourClient
    .mutate({mutation: mutations.followUser, variables: {userId: theirUserId}})
    .then(({data}) => expect(data.followUser.followedStatus).toBe('FOLLOWING'))
  await otherClient
    .mutate({mutation: mutations.followUser, variables: {userId: theirUserId}})
    .then(({data}) => expect(data.followUser.followedStatus).toBe('FOLLOWING'))

  // let the system finish processing those followings
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.self})
    expect(data.self.followersCount).toBe(2)
    expect(data.self.followerUsers.items).toHaveLength(2)
  })

  // they add a message with bad word
  const messageId3 = uuidv4()
  variables = {chatId, messageId: messageId3, text: `m3 ${badWord}`}
  await theirClient
    .mutate({mutation: mutations.addChatMessage, variables})
    .then(({data: {addChatMessage: chatMessage}}) => {
      expect(chatMessage.messageId).toBe(messageId3)
    })

  // verify other can see all messages
  await eventually(async () => {
    const {data} = await otherClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.messagesCount).toBe(7)
    expect(data.chat.messages.items).toHaveLength(7)
    expect(data.chat.messages.items.slice(0, 5).map((item) => item.messageId)).toEqual(first5MessageIds)
    expect(data.chat.messages.items[5].messageId).toBe(messageId2)
    expect(data.chat.messages.items[6].messageId).toBe(messageId3)
  })

  // we add a message with bad word
  const messageId4 = uuidv4()
  variables = {chatId, messageId: messageId4, text: `m4 ${badWord}`}
  await ourClient
    .mutate({mutation: mutations.addChatMessage, variables})
    .then(({data: {addChatMessage: chatMessage}}) => {
      expect(chatMessage.messageId).toBe(messageId4)
    })

  // verify our bad chat message is removed
  await sleep()
  await ourClient.query({query: queries.chat, variables: {chatId}}).then(({data}) => {
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.messagesCount).toBe(7)
    expect(data.chat.messages.items).toHaveLength(7)
    expect(data.chat.messages.items.slice(0, 5).map((item) => item.messageId)).toEqual(first5MessageIds)
    expect(data.chat.messages.items[5].messageId).toBe(messageId2)
    expect(data.chat.messages.items[6].messageId).toBe(messageId3)
  })
})
