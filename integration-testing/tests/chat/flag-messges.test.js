import {v4 as uuidv4} from 'uuid'

import {cognito, eventually} from '../../utils'
import {mutations, queries} from '../../schema'

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Flag message failures', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: other1Client, userId: other1UserId} = await loginCache.getCleanLogin()
  const {client: other2Client} = await loginCache.getCleanLogin()
  const mutation = mutations.flagChatMessage

  // we create a group chat with us and other1 in it
  const [chatId, messageId1] = [uuidv4(), uuidv4()]
  await ourClient.mutate({
    mutation: mutations.createGroupChat,
    variables: {chatId, userIds: [other1UserId], messageId: messageId1, messageText: 'm1'},
  })

  const systemMessageId = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId, messagesCount: 4}})
    expect(data.chat.messages.items[3].messageId).toBe(messageId1)
    return data.chat.messages.items[0].messageId
  })

  // other1 adds a message
  const messageId2 = uuidv4()
  await other1Client
    .mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: messageId2, text: 'm2'}})
    .then(({data}) => expect(data.addChatMessage.messageId).toBe(messageId2))

  // can't flag a message that DNE
  const messageId3 = uuidv4()
  await expect(other1Client.mutate({mutation, variables: {messageId: messageId3}})).rejects.toThrow(
    /ChatMessage .* does not exist/,
  )

  // cant' flag a system message
  await expect(ourClient.mutate({mutation, variables: {messageId: systemMessageId}})).rejects.toThrow(
    /Cannot flag system chat message/,
  )

  // can't flag our own message
  await expect(ourClient.mutate({mutation, variables: {messageId: messageId1}})).rejects.toThrow(
    /User cant flag their own/,
  )

  // can't flag message of a chat user is not in
  await expect(other2Client.mutate({mutation, variables: {messageId: messageId1}})).rejects.toThrow(
    /User is not part of chat/,
  )

  // blocking relationships block flagging both ways
  await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: other1UserId}}).then(({data}) => {
    expect(data.blockUser.userId).toBe(other1UserId)
    expect(data.blockUser.blockedStatus).toBe('BLOCKING')
  })
  await expect(ourClient.mutate({mutation, variables: {messageId: messageId2}})).rejects.toThrow(
    /User has blocked owner of chatMessage/,
  )
  await expect(other1Client.mutate({mutation, variables: {messageId: messageId1}})).rejects.toThrow(
    /User has been blocked by owner of chatMessage/,
  )
  await ourClient.mutate({mutation: mutations.unblockUser, variables: {userId: other1UserId}}).then(({data}) => {
    expect(data.unblockUser.userId).toBe(other1UserId)
    expect(data.unblockUser.blockedStatus).toBe('NOT_BLOCKING')
  })

  // can't flag a message if we're disabled
  await other1Client.mutate({mutation: mutations.disableUser}).then(({data}) => {
    expect(data.disableUser.userId).toBe(other1UserId)
    expect(data.disableUser.userStatus).toBe('DISABLED')
  })
  await expect(other1Client.mutate({mutation, variables: {messageId: messageId1}})).rejects.toThrow(
    /User .* is not ACTIVE/,
  )

  // can't double flag message - can't test this as without 10+ members in the chat,
  // every message that is flagged is immediately force-deleted
})

test('Flag message success', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // we create a direct chat with them
  const [chatId, messageId] = [uuidv4(), uuidv4()]
  await ourClient.mutate({
    mutation: mutations.createDirectChat,
    variables: {userId: theirUserId, chatId, messageId, messageText: 'lore ipsum'},
  })

  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId}})
    expect(data.chat.messages.items.map((i) => i.messageId)).toContain(messageId)
  })

  // check they see our message as unflagged
  await theirClient.query({query: queries.chat, variables: {chatId}}).then(({data}) => {
    expect(data.chat.messages.items[0].messageId).toBe(messageId)
    expect(data.chat.messages.items[0].flagStatus).toBe('NOT_FLAGGED')
  })

  // they flag our message
  await theirClient.mutate({mutation: mutations.flagChatMessage, variables: {messageId}}).then(({data}) => {
    expect(data.flagChatMessage.messageId).toBe(messageId)
    expect(data.flagChatMessage.flagStatus).toBe('FLAGGED')
  })

  // met force removal criteria, message is deleted
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.chat, variables: {chatId}})
    expect(data.chat.flagStatus).toBe('FLAGGED')
    expect(data.chat.messages.items).toHaveLength(0)
  })
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data.chat.messages.items).toHaveLength(0)
  })
})

test('User disabled from flagged messages', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // we create a direct chat with them
  const [chatId, messageId] = [uuidv4(), uuidv4()]
  await ourClient.mutate({
    mutation: mutations.createDirectChat,
    variables: {userId: theirUserId, chatId, messageId, messageText: 'lore ipsum'},
  })

  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId, usersCount: 2, messagesCount: 1}})
  })

  // we add five more messages to the chat
  let messageId2
  for (const i of Array(5).keys()) {
    messageId2 = uuidv4()
    await ourClient
      .mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: messageId2, text: 'msg ' + i}})
      .then(({data}) => expect(data.addChatMessage.messageId).toBeTruthy())
  }
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId}})
    expect(data).toMatchObject({chat: {chatId, usersCount: 2, messagesCount: 6}})
  })

  // they flag one of our messages
  await theirClient.mutate({mutation: mutations.flagChatMessage, variables: {messageId}}).then(({data}) => {
    expect(data.flagChatMessage.messageId).toBe(messageId)
    expect(data.flagChatMessage.flagStatus).toBe('FLAGGED')
  })

  // chat still exists
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.chat, variables: {chatId}})
    expect(data.chat.chatId).toBe(chatId)
  })

  // they flag other message again
  await theirClient
    .mutate({mutation: mutations.flagChatMessage, variables: {messageId: messageId2}})
    .then(({data}) => {
      expect(data.flagChatMessage.messageId).toBe(messageId2)
      expect(data.flagChatMessage.flagStatus).toBe('FLAGGED')
    })

  // chat is not longer available
  await expect(
    theirClient.mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: uuidv4(), text: 'a'}}),
  ).rejects.toThrow(/Chat .* does not exist/)

  // that catches the auto-disabling criteria, check we were disabled
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userStatus).toBe('DISABLED')
  })
})

test('Chat force deleted from combined assets - (chat messages, posts)', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()
  const {client: otherClient, userId: otherUserId} = await loginCache.getCleanLogin()

  // we create two group chats with them and other
  const [chatId1, chatId2, messageId1, messageId2] = [uuidv4(), uuidv4(), uuidv4(), uuidv4()]
  await ourClient.mutate({
    mutation: mutations.createGroupChat,
    variables: {chatId: chatId1, userIds: [theirUserId, otherUserId], messageId: messageId1, messageText: 'm1'},
  })
  await ourClient.mutate({
    mutation: mutations.createGroupChat,
    variables: {chatId: chatId2, userIds: [theirUserId, otherUserId], messageId: messageId2, messageText: 'm2'},
  })

  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId: chatId1}})
    expect(data).toMatchObject({chat: {chatId: chatId1, usersCount: 3, messagesCount: 5}})
  })

  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.chat, variables: {chatId: chatId2}})
    expect(data).toMatchObject({chat: {chatId: chatId2, usersCount: 3, messagesCount: 5}})
  })

  // we create three posts
  for (const i of Array(3).keys()) {
    await ourClient
      .mutate({
        mutation: mutations.addPost,
        variables: {postId: uuidv4(), postType: 'TEXT_ONLY', text: `lore ipsum-${i}`},
      })
      .then(({data: {addPost: post}}) => {
        expect(post.postId).toBeTruthy()
        expect(post.postStatus).toBe('COMPLETED')
      })
  }
  // they and other flag our message, check chat is force deleted, we are still alive
  await theirClient
    .mutate({mutation: mutations.flagChatMessage, variables: {messageId: messageId1}})
    .then(({data}) => {
      expect(data.flagChatMessage.messageId).toBe(messageId1)
      expect(data.flagChatMessage.flagStatus).toBe('FLAGGED')
    })
  await otherClient
    .mutate({mutation: mutations.flagChatMessage, variables: {messageId: messageId1}})
    .then(({data}) => {
      expect(data.flagChatMessage.messageId).toBe(messageId1)
      expect(data.flagChatMessage.flagStatus).toBe('FLAGGED')
    })

  await expect(
    ourClient.mutate({
      mutation: mutations.addChatMessage,
      variables: {chatId: chatId1, messageId: uuidv4(), text: 'a'},
    }),
  ).rejects.toThrow(/Chat .* does not exist/)

  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userStatus).toBe('ACTIVE')
  })

  // they and other flag our message in other chat, check chat is force deleted
  await theirClient
    .mutate({mutation: mutations.flagChatMessage, variables: {messageId: messageId2}})
    .then(({data}) => {
      expect(data.flagChatMessage.messageId).toBe(messageId2)
      expect(data.flagChatMessage.flagStatus).toBe('FLAGGED')
    })
  await otherClient
    .mutate({mutation: mutations.flagChatMessage, variables: {messageId: messageId2}})
    .then(({data}) => {
      expect(data.flagChatMessage.messageId).toBe(messageId2)
      expect(data.flagChatMessage.flagStatus).toBe('FLAGGED')
    })

  await expect(
    ourClient.mutate({
      mutation: mutations.addChatMessage,
      variables: {chatId: chatId2, messageId: uuidv4(), text: 'a'},
    }),
  ).rejects.toThrow(/Chat .* does not exist/)
})
