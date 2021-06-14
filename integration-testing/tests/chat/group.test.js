import dayjs from 'dayjs'
import {v4 as uuidv4} from 'uuid'

import {cognito, eventually, sleep} from '../../utils'
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

test('Create and edit a group chat', async () => {
  const {client: ourClient, userId: ourUserId, username: ourUsername} = await loginCache.getCleanLogin()
  const {client: other1Client, userId: other1UserId, username: other1Username} = await loginCache.getCleanLogin()
  const {client: other2Client, userId: other2UserId, username: other2Username} = await loginCache.getCleanLogin()

  // we create a group chat with all of us in it, check details are correct
  const [chatId, messageId1] = [uuidv4(), uuidv4()]
  const before = dayjs().toISOString()
  await ourClient
    .mutate({
      mutation: mutations.createGroupChat,
      variables: {
        chatId,
        name: 'x',
        userIds: [other1UserId, other2UserId],
        messageId: messageId1,
        messageText: 'm',
      },
    })
    .then(({data}) => expect(data.createGroupChat.chatId).toBe(chatId))
  const after = dayjs().toISOString()

  const firstMessageIds = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId, chatType: 'GROUP', name: 'x'}})
    expect(data.chat.createdAt > before).toBe(true)
    expect(data.chat.createdAt < after).toBe(true)
    expect(data.chat.createdAt < data.chat.lastMessageActivityAt).toBe(true)
    expect(data.chat.usersCount).toBe(3)
    expect(data.chat.users.items.map((u) => u.userId).sort()).toEqual(
      [ourUserId, other1UserId, other2UserId].sort(),
    )
    expect(data.chat.messagesCount).toBe(5)
    expect(data.chat.messages.items).toHaveLength(5)
    expect(data.chat.messages.items[0].authorUserId).toBeNull()
    expect(data.chat.messages.items[0].text).toContain(ourUsername)
    expect(data.chat.messages.items[0].text).toContain('created the group')
    expect(data.chat.messages.items[0].text).toContain('x')
    expect(data.chat.messages.items[0].textTaggedUsers).toHaveLength(1)
    expect(data.chat.messages.items[0].textTaggedUsers[0].tag).toBe(`@${ourUsername}`)
    expect(data.chat.messages.items[0].textTaggedUsers[0].user.userId).toBe(ourUserId)
    expect(data.chat.messages.items[1].authorUserId).toBeNull()
    expect(data.chat.messages.items[1].text).toContain('was added to the group')
    expect(data.chat.messages.items[1].text).toContain(ourUsername)
    // order of these two messages is undefined
    const [o1Msg, o2Msg] = data.chat.messages.items
      .slice(2, 4)
      .sort((m) => (m.textTaggedUsers[0].user.userId == other1UserId ? -1 : 1))
    expect(o1Msg.authorUserId).toBeNull()
    expect(o1Msg.text).toContain('was added to the group')
    expect(o1Msg.text).toContain(other1Username)
    expect(o2Msg.authorUserId).toBeNull()
    expect(o2Msg.text).toContain('was added to the group')
    expect(o2Msg.text).toContain(other2Username)
    expect(data.chat.messages.items[4].messageId).toBe(messageId1)
    expect(data.chat.messages.items[4].authorUserId).toBe(ourUserId)
    expect(data.chat.messages.items[4].text).toBe('m')
    return data.chat.messages.items.map((item) => item.messageId)
  })

  // check we have the chat
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.chatCount).toBe(1)
    expect(data.self.chats.items).toHaveLength(1)
    expect(data.self.chats.items[0].chatId).toBe(chatId)
  })

  // check other1 has the chat
  await other1Client.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(other1UserId)
    expect(data.self.chatCount).toBe(1)
    expect(data.self.chats.items).toHaveLength(1)
    expect(data.self.chats.items[0].chatId).toBe(chatId)
  })

  // we add a message
  const messageId2 = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: messageId2, text: 'm2'}})
    .then(({data}) => expect(data.addChatMessage.messageId).toBe(messageId2))

  // other1 adds a message
  const messageId3 = uuidv4()
  await other1Client
    .mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: messageId3, text: 'm3'}})
    .then(({data}) => expect(data.addChatMessage.messageId).toBe(messageId3))

  // check other2 sees both those messages
  const secondMessageIds = await eventually(async () => {
    const {data} = await other2Client.query({query: queries.chat, variables: {chatId}})
    expect(data.chat.messagesCount).toBe(7)
    expect(data.chat.messages.items).toHaveLength(7)
    expect(data.chat.messages.items.slice(0, 5).map((item) => item.messageId)).toEqual(firstMessageIds)
    expect(data.chat.messages.items[5].messageId).toBe(messageId2)
    expect(data.chat.messages.items[5].authorUserId).toBe(ourUserId)
    expect(data.chat.messages.items[6].messageId).toBe(messageId3)
    expect(data.chat.messages.items[6].authorUserId).toBe(other1UserId)
    return data.chat.messages.items.slice(5).map((item) => item.messageId)
  })

  // other2 edits the name of the group chat
  const name = uuidv4()
  await other2Client.mutate({mutation: mutations.editGroupChat, variables: {chatId, name}}).then(({data}) => {
    expect(data.editGroupChat.chatId).toBe(chatId)
    expect(data.editGroupChat.name).toBe(name)
  })

  // check we see the updated name and the messages
  const thirdMessageId = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data.chat.name).toBe(name)
    expect(data.chat.messagesCount).toBe(8)
    expect(data.chat.messages.items).toHaveLength(8)
    expect(data.chat.messages.items.slice(0, 5).map((item) => item.messageId)).toEqual(firstMessageIds)
    expect(data.chat.messages.items.slice(5, 7).map((item) => item.messageId)).toEqual(secondMessageIds)
    expect(data.chat.messages.items[7].authorUserId).toBeNull()
    expect(data.chat.messages.items[7].text).toContain('name of the group was changed to')
    expect(data.chat.messages.items[7].text).toContain(name)
    expect(data.chat.messages.items[7].textTaggedUsers).toEqual([])
    return data.chat.messages.items[7].messageId
  })

  // we delete the name of the group chat
  await ourClient.mutate({mutation: mutations.editGroupChat, variables: {chatId, name: ''}}).then(({data}) => {
    expect(data.editGroupChat.chatId).toBe(chatId)
    expect(data.editGroupChat.name).toBeNull()
  })

  // check other1 sees the updated name
  await eventually(async () => {
    const {data} = await other1Client.query({query: queries.chat, variables: {chatId}})
    expect(data.chat.name).toBeNull()
    expect(data.chat.messagesCount).toBe(9)
    expect(data.chat.messages.items).toHaveLength(9)
    expect(data.chat.messages.items.slice(0, 5).map((item) => item.messageId)).toEqual(firstMessageIds)
    expect(data.chat.messages.items.slice(5, 7).map((item) => item.messageId)).toEqual(secondMessageIds)
    expect(data.chat.messages.items[7].messageId).toBe(thirdMessageId)
    expect(data.chat.messages.items[8].author).toBeNull()
    expect(data.chat.messages.items[8].text).toContain('name of the group was deleted')
    expect(data.chat.messages.items[8].textTaggedUsers).toEqual([])
  })
})

test('Creating a group chat with our userId in the listed userIds has no affect', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {userId: theirUserId} = await loginCache.getCleanLogin()

  // we create a group chat with the two of us in it, and we uncessarily add our user Id to the userIds
  const [chatId, messageId] = [uuidv4(), uuidv4()]
  await ourClient
    .mutate({
      mutation: mutations.createGroupChat,
      variables: {chatId, userIds: [ourUserId, theirUserId], messageId, messageText: 'm1'},
    })
    .then(({data}) => expect(data.createGroupChat.chatId).toBe(chatId))

  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId, name: null}})
    expect(data.chat.usersCount).toBe(2)
    expect(data.chat.users.items.map((u) => u.userId).sort()).toEqual([ourUserId, theirUserId].sort())
  })
})

test('Cannot create, edit, add others to or leave a group chat if we are disabled', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {userId: theirUserId} = await loginCache.getCleanLogin()

  // we create a group chat with just us in it
  const chatId = uuidv4()
  let variables = {chatId, userIds: [], messageId: uuidv4(), messageText: 'm1'}
  let resp = await ourClient.mutate({mutation: mutations.createGroupChat, variables})
  expect(resp.data.createGroupChat.chatId).toBe(chatId)

  // we disable ourselves
  resp = await ourClient.mutate({mutation: mutations.disableUser})
  expect(resp.data.disableUser.userId).toBe(ourUserId)
  expect(resp.data.disableUser.userStatus).toBe('DISABLED')

  // verify we cannot create another group chat
  variables = {chatId: uuidv4(), userIds: [], messageId: uuidv4(), messageText: 'm1'}
  await expect(ourClient.mutate({mutation: mutations.createGroupChat, variables})).rejects.toThrow(
    /ClientError: User .* is not ACTIVE/,
  )

  // verify we cannot add someone else to our existing group chat
  await expect(
    ourClient.mutate({mutation: mutations.addToGroupChat, variables: {chatId, userIds: [theirUserId]}}),
  ).rejects.toThrow(/ClientError: User .* is not ACTIVE/)

  // verify we cannot edit our existing group chat
  await expect(
    ourClient.mutate({mutation: mutations.editGroupChat, variables: {chatId, name: 'new'}}),
  ).rejects.toThrow(/ClientError: User .* is not ACTIVE/)

  // verify we cannot leave our existing group chat
  await expect(ourClient.mutate({mutation: mutations.leaveGroupChat, variables: {chatId}})).rejects.toThrow(
    /ClientError: User .* is not ACTIVE/,
  )
})

test('Anonymous users cannot create nor get added to a group chat', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {userId: theirUserId} = await loginCache.getCleanLogin()
  const {userId: otherUserId} = await loginCache.getCleanLogin()
  ;({client: anonClient, userId: anonUserId} = await cognito.getAnonymousAppSyncLogin())

  // verify anonymous user can't create group chat
  const chatId = uuidv4()
  await expect(
    anonClient.mutate({
      mutation: mutations.createGroupChat,
      variables: {chatId, userIds: [], messageId: uuidv4(), messageText: 'm1'},
    }),
  ).rejects.toThrow(/ClientError: User .* is not ACTIVE/)

  // verify if we create a group chat with an anonymous user, they actually don't get added
  await ourClient
    .mutate({
      mutation: mutations.createGroupChat,
      variables: {chatId, userIds: [anonUserId, theirUserId], messageId: uuidv4(), messageText: 'm2'},
    })
    .then(({data: {createGroupChat: chat}}) => expect(chat.chatId).toBe(chatId))
  await sleep()
  await ourClient.query({query: queries.chatUsers, variables: {chatId}}).then(({data: {chat}}) => {
    expect(chat.chatId).toBe(chatId)
    expect(chat.usersCount).toBe(2)
    expect(chat.users.items).toHaveLength(2)
    expect(chat.users.items.map((u) => u.userId).sort()).toEqual([ourUserId, theirUserId].sort())
  })

  // verify if we try to add the anonymous user to a group chat, they don't get added
  await ourClient.mutate({
    mutation: mutations.addToGroupChat,
    variables: {chatId, userIds: [anonUserId, otherUserId]},
  })
  await sleep()
  await ourClient.query({query: queries.chatUsers, variables: {chatId}}).then(({data: {chat}}) => {
    expect(chat.chatId).toBe(chatId)
    expect(chat.usersCount).toBe(3)
    expect(chat.users.items).toHaveLength(3)
    expect(chat.users.items.map((u) => u.userId).sort()).toEqual([ourUserId, theirUserId, otherUserId].sort())
  })
})

test('Exclude users from list of users in a chat', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {userId: theirUserId} = await loginCache.getCleanLogin()

  // we create a group chat with the two of us in it
  const [chatId, messageId] = [uuidv4(), uuidv4()]
  await ourClient
    .mutate({
      mutation: mutations.createGroupChat,
      variables: {chatId, userIds: [theirUserId], messageId, messageText: 'm1'},
    })
    .then(({data}) => expect(data.createGroupChat.chatId).toBe(chatId))

  // check chat users, all included
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chatUsers, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.usersCount).toBe(2)
    expect(data.chat.users.items).toHaveLength(2)
    expect(data.chat.users.items.map((u) => u.userId).sort()).toEqual([ourUserId, theirUserId].sort())
  })

  // exclude ourselves
  await ourClient
    .query({query: queries.chatUsers, variables: {chatId, excludeUserId: ourUserId}})
    .then(({data}) => {
      expect(data).toMatchObject({chat: {chatId}})
      expect(data.chat.usersCount).toBe(2)
      expect(data.chat.users.items).toHaveLength(1)
      expect(data.chat.users.items[0].userId).toBe(theirUserId)
    })

  // exclude them
  await ourClient
    .query({query: queries.chatUsers, variables: {chatId, excludeUserId: theirUserId}})
    .then(({data}) => {
      expect(data).toMatchObject({chat: {chatId}})
      expect(data.chat.usersCount).toBe(2)
      expect(data.chat.users.items).toHaveLength(1)
      expect(data.chat.users.items[0].userId).toBe(ourUserId)
    })
})

test('Create a group chat with just us and without a name, add people to it and leave from it', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId, username: theirUsername} = await loginCache.getCleanLogin()
  const {client: otherClient, userId: otherUserId, username: otherUsername} = await loginCache.getCleanLogin()

  // we create a group chat with no name and just us in it
  const [chatId, messageId1] = [uuidv4(), uuidv4()]
  await ourClient
    .mutate({
      mutation: mutations.createGroupChat,
      variables: {chatId, userIds: [], messageId: messageId1, messageText: 'm1'},
    })
    .then(({data}) => expect(data.createGroupChat.chatId).toBe(chatId))

  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId, name: null}})
    expect(data.chat.usersCount).toBe(1)
    expect(data.chat.users.items).toHaveLength(1)
    expect(data.chat.users.items[0].userId).toBe(ourUserId)
    expect(data.chat.messagesCount).toBe(3)
    expect(data.chat.messages.items).toHaveLength(3)
    expect(data.chat.messages.items[2].messageId).toBe(messageId1)
  })

  // check they can't access the chat
  await theirClient
    .query({query: queries.chat, variables: {chatId}})
    .then(({data}) => expect(data.chat).toBeNull())

  // we add them and other to the chat
  await ourClient.mutate({
    mutation: mutations.addToGroupChat,
    variables: {chatId, userIds: [theirUserId, otherUserId]},
  })
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.usersCount).toBe(3)
    expect(data.chat.users.items.map((u) => u.userId).sort()).toEqual(
      [ourUserId, theirUserId, otherUserId].sort(),
    )
    expect(data.chat.messagesCount).toBe(5)
    expect(data.chat.messages.items).toHaveLength(5)
    expect(data.chat.messages.items[2].messageId).toBe(messageId1)
    // the order in which these two messages are added is not defined
    const [theirMessage, otherMessage] = data.chat.messages.items
      .slice(3, 5)
      .sort((m) => (m.textTaggedUsers[0].user.userId == theirUserId ? -1 : 1))
    expect(theirMessage.text).toContain(theirUsername)
    expect(theirMessage.text).toContain('was added to the group')
    expect(theirMessage.textTaggedUsers).toHaveLength(1)
    expect(theirMessage.textTaggedUsers[0].user.userId).toBe(theirUserId)
    expect(otherMessage.text).toContain(otherUsername)
    expect(otherMessage.text).toContain('was added to the group')
    expect(otherMessage.textTaggedUsers).toHaveLength(1)
    expect(otherMessage.textTaggedUsers[0].user.userId).toBe(otherUserId)
  })

  // check they have the chat now
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.self})
    expect(data.self.userId).toBe(theirUserId)
    expect(data.self.chatCount).toBe(1)
    expect(data.self.chats.items).toHaveLength(1)
    expect(data.self.chats.items[0].chatId).toBe(chatId)
    expect(data.self.chats.items[0].messagesCount).toBe(5)
  })

  // check other can directly access the chat
  await otherClient
    .query({query: queries.chat, variables: {chatId}})
    .then(({data}) => expect(data).toMatchObject({chat: {chatId}}))

  // they add a message to the chat
  const messageId2 = uuidv4()
  await theirClient
    .mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: messageId2, text: 'lore'}})
    .then(({data}) => expect(data.addChatMessage.messageId).toBe(messageId2))

  // they leave the chat
  await theirClient
    .mutate({mutation: mutations.leaveGroupChat, variables: {chatId}})
    .then(({data}) => expect(data.leaveGroupChat.chatId).toBe(chatId))

  // check we see their message, we don't see them in the chat
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.usersCount).toBe(2)
    expect(data.chat.users.items).toHaveLength(2)
    expect(data.chat.users.items.map((u) => u.userId).sort()).toEqual([ourUserId, otherUserId].sort())
    expect(data.chat.messagesCount).toBe(7)
    expect(data.chat.messages.items).toHaveLength(7)
    expect(data.chat.messages.items[2].messageId).toBe(messageId1)
    expect(data.chat.messages.items[5].messageId).toBe(messageId2)
    expect(data.chat.messages.items[6].text).toContain(theirUsername)
    expect(data.chat.messages.items[6].text).toContain('left the group')
    expect(data.chat.messages.items[6].textTaggedUsers).toHaveLength(1)
    expect(data.chat.messages.items[6].textTaggedUsers[0].user.userId).toBe(theirUserId)
  })

  // we leave the chat
  await ourClient
    .mutate({mutation: mutations.leaveGroupChat, variables: {chatId}})
    .then(({data}) => expect(data.leaveGroupChat.chatId).toBe(chatId))

  // check we can no longer access the chat
  await ourClient.query({query: queries.chat, variables: {chatId}}).then(({data}) => expect(data.chat).toBeNull())
})

test('Cant add a users that does not exist to a group', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {userId: theirUserId} = await loginCache.getCleanLogin()

  // we create a group chat with us and another non-existent user in it,
  // should skip over the non-existent user
  const [chatId, messageId] = [uuidv4(), uuidv4()]
  await ourClient.mutate({
    mutation: mutations.createGroupChat,
    variables: {chatId, userIds: ['uid-dne'], messageId, messageText: 'm1'},
  })
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.usersCount).toBe(1)
    expect(data.chat.users.items[0].userId).toBe(ourUserId)
    expect(data.chat.messagesCount).toBe(3)
    expect(data.chat.messages.items).toHaveLength(3)
    expect(data.chat.messages.items[2].messageId).toBe(messageId)
  })

  // add another non-existent user to the group, as well as a good one
  // should skip over the non-existent user
  await ourClient.mutate({
    mutation: mutations.addToGroupChat,
    variables: {chatId, userIds: [theirUserId, 'uid-dne1', 'uid-dne2']},
  })
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.usersCount).toBe(2)
    expect(data.chat.users.items.map((u) => u.userId).sort()).toEqual([ourUserId, theirUserId].sort())
    expect(data.chat.messagesCount).toBe(4)
    expect(data.chat.messages.items).toHaveLength(4)
    expect(data.chat.messages.items[2].messageId).toBe(messageId)
    expect(data.chat.messages.items[3].text).toContain('added')
    expect(data.chat.messages.items[3].textTaggedUsers).toHaveLength(1)
    expect(data.chat.messages.items[3].textTaggedUsers[0].user.userId).toBe(theirUserId)
  })
})

test('Add someone to a group chat that is already there is a no-op', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {userId: other1UserId} = await loginCache.getCleanLogin()
  const {userId: other2UserId} = await loginCache.getCleanLogin()

  // we create a group chat with both of us in it
  const chatId = uuidv4()
  await ourClient
    .mutate({
      mutation: mutations.createGroupChat,
      variables: {chatId, userIds: [other1UserId], messageId: uuidv4(), messageText: 'm1'},
    })
    .then(({data}) => expect(data.createGroupChat.chatId).toBe(chatId))
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.usersCount).toBe(2)
    expect(data.chat.users.items.map((u) => u.userId).sort()).toEqual([ourUserId, other1UserId].sort())
  })

  // check adding to them to the chat again does nothing
  await ourClient
    .mutate({mutation: mutations.addToGroupChat, variables: {chatId, userIds: [other1UserId]}})
    .then(({data}) => expect(data.addToGroupChat.chatId).toBe(chatId))
  await sleep()
  await ourClient.query({query: queries.chat, variables: {chatId}}).then(({data}) => {
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.usersCount).toBe(2)
    expect(data.chat.users.items.map((u) => u.userId).sort()).toEqual([ourUserId, other1UserId].sort())
  })

  // check adding to them and another user to the chat at the same time adds the other user
  await ourClient
    .mutate({
      mutation: mutations.addToGroupChat,
      variables: {chatId, userIds: [other1UserId, other2UserId]},
    })
    .then(({data}) => expect(data.addToGroupChat.chatId).toBe(chatId))
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.usersCount).toBe(3)
    expect(data.chat.users.items.map((u) => u.userId).sort()).toEqual(
      [ourUserId, other1UserId, other2UserId].sort(),
    )
  })
})

test('Cannot add someone to a chat that DNE, that we are not in or that is a a direct chat', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: other1Client, userId: other1UserId} = await loginCache.getCleanLogin()
  const {userId: other2UserId} = await loginCache.getCleanLogin()

  // check we can't add other1 to a chat that DNE
  await ourClient
    .mutate({
      mutation: mutations.addToGroupChat,
      variables: {chatId: uuidv4(), userIds: [other1UserId]},
      errorPolicy: 'all',
    })
    .then(({errors}) => {
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toMatch(/ClientError: .* is not a member/)
    })

  // other1 creates a group chat with only themselves in it
  const chatId1 = uuidv4()
  await other1Client.mutate({
    mutation: mutations.createGroupChat,
    variables: {chatId: chatId1, userIds: [], messageId: uuidv4(), messageText: 'm'},
  })
  await eventually(async () => {
    const {data} = await other1Client.query({query: queries.chat, variables: {chatId: chatId1}})
    expect(data).toMatchObject({chat: {chatId: chatId1, usersCount: 1}})
  })

  // check we cannot add other2 to that group chat
  await ourClient
    .mutate({
      mutation: mutations.addToGroupChat,
      variables: {chatId: chatId1, userIds: [other2UserId]},
      errorPolicy: 'all',
    })
    .then(({errors}) => {
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toMatch(/ClientError: .* is not a member/)
    })

  // we create a direct chat with other2
  const chatId2 = uuidv4()
  await ourClient.mutate({
    mutation: mutations.createDirectChat,
    variables: {userId: other2UserId, chatId: chatId2, messageId: uuidv4(), messageText: 'lore ipsum'},
  })

  // check we cannot add other1 to that direct chat
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId: chatId2}})
    expect(data).toMatchObject({chat: {chatId: chatId2}})
  })
  await ourClient
    .mutate({
      mutation: mutations.addToGroupChat,
      variables: {chatId: chatId2, userIds: [other1UserId]},
      errorPolicy: 'all',
    })
    .then(({errors}) => {
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toMatch(/ClientError: Cannot add users to non-GROUP chat /)
    })
})

test('Cannot leave a chat that DNE, that we are not in, or that is a direct chat', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // check we cannot leave a chat that DNE
  await ourClient
    .mutate({mutation: mutations.leaveGroupChat, variables: {chatId: uuidv4()}, errorPolicy: 'all'})
    .then(({errors}) => {
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toMatch(/ClientError: .* is not a member/)
    })

  // they create a group chat with only themselves in it
  const chatId1 = uuidv4()
  await theirClient.mutate({
    mutation: mutations.createGroupChat,
    variables: {chatId: chatId1, userIds: [], messageId: uuidv4(), messageText: 'm'},
  })
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.chat, variables: {chatId: chatId1}})
    expect(data).toMatchObject({chat: {chatId: chatId1, usersCount: 1}})
  })

  // check we cannot leave from that group chat we are not in
  await ourClient
    .mutate({mutation: mutations.leaveGroupChat, variables: {chatId: chatId1}, errorPolicy: 'all'})
    .then(({errors}) => {
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toMatch(/ClientError: .* is not a member/)
    })

  // we create a direct chat with them
  const chatId2 = uuidv4()
  await ourClient.mutate({
    mutation: mutations.createDirectChat,
    variables: {userId: theirUserId, chatId: chatId2, messageId: uuidv4(), messageText: 'lore ipsum'},
  })
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId: chatId2}})
    expect(data).toMatchObject({chat: {chatId: chatId2, usersCount: 2}})
  })

  // check we cannot leave that direct chat
  await ourClient
    .mutate({mutation: mutations.leaveGroupChat, variables: {chatId: chatId2}, errorPolicy: 'all'})
    .then(({errors}) => {
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toMatch(/ClientError: Cannot leave non-GROUP chat /)
    })
})

test('Cannnot edit name of chat that DNE, that we are not in, or that is a direct chat', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // check we cannot edit a chat that DNE
  await ourClient
    .mutate({
      mutation: mutations.leaveGroupChat,
      variables: {chatId: uuidv4(), name: 'new name'},
      errorPolicy: 'all',
    })
    .then(({errors}) => {
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toMatch(/ClientError: .* is not a member/)
    })

  // they create a group chat with only themselves in it
  const chatId1 = uuidv4()
  await theirClient.mutate({
    mutation: mutations.createGroupChat,
    variables: {chatId: chatId1, userIds: [], messageId: uuidv4(), messageText: 'm'},
  })
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.chat, variables: {chatId: chatId1}})
    expect(data).toMatchObject({chat: {chatId: chatId1, usersCount: 1}})
  })

  // check we cannot edit the name of their group chat
  await ourClient
    .mutate({
      mutation: mutations.editGroupChat,
      variables: {chatId: chatId1, name: 'chat name'},
      errorPolicy: 'all',
    })
    .then(({errors}) => {
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toMatch(/ClientError: .* is not a member/)
    })

  // we create a direct chat with them
  const chatId2 = uuidv4()
  await ourClient.mutate({
    mutation: mutations.createDirectChat,
    variables: {userId: theirUserId, chatId: chatId2, messageId: uuidv4(), messageText: 'lore ipsum'},
  })
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId: chatId2}})
    expect(data).toMatchObject({chat: {chatId: chatId2, usersCount: 2}})
  })

  // check we cannot edit the name of that direct chat
  await ourClient
    .mutate({
      mutation: mutations.editGroupChat,
      variables: {chatId: chatId2, name: 'chat name'},
      errorPolicy: 'all',
    })
    .then(({errors}) => {
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toMatch(/ClientError: Cannot edit non-GROUP chat /)
    })
})
