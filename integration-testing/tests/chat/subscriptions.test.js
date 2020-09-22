const fs = require('fs')
const moment = require('moment')
const path = require('path')
const uuidv4 = require('uuid/v4')
// the aws-appsync-subscription-link pacakge expects WebSocket to be globaly defined, like in the browser
global.WebSocket = require('ws')

const cognito = require('../../utils/cognito')
const misc = require('../../utils/misc')
const {mutations, subscriptions} = require('../../schema')

const grantData = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg'))
const grantDataB64 = new Buffer.from(grantData).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()
jest.retryTimes(1)

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Chat message triggers cannot be called from external graphql client', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()

  // they open up a chat with us
  const [chatId, messageId] = [uuidv4(), uuidv4()]
  await theirClient
    .mutate({
      mutation: mutations.createDirectChat,
      variables: {userId: ourUserId, chatId, messageId, messageText: 'lore ipsum'},
    })
    .then(({data: {createDirectChat: chat}}) => {
      expect(chat.chatId).toBe(chatId)
      expect(chat.messages.items).toHaveLength(1)
      expect(chat.messages.items[0].messageId).toBe(messageId)
    })

  // create a well-formed valid chat notification object
  // verify niether of us can call the trigger method, even with a valid chat & message id
  const mutation = mutations.triggerChatMessageNotification
  const variables = {
    input: {
      userId: ourUserId,
      messageId,
      chatId,
      authorUserId: ourUserId,
      type: 'ADDED',
      text: 'lore ipsum',
      textTaggedUserIds: [],
      createdAt: moment().toISOString(),
    },
  }
  await expect(ourClient.mutate({mutation, variables})).rejects.toThrow(/ClientError: Access denied/)
  await expect(theirClient.mutate({mutation, variables})).rejects.toThrow(/ClientError: Access denied/)
})

test('Cannot subscribe to other users messages', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // verify we cannot subscribe to their messages
  // Note: there doesn't seem to be any error thrown at the time of subscription, it's just that
  // the subscription next() method is never triggered
  const msgNotifications = []
  await ourClient
    .subscribe({query: subscriptions.onChatMessageNotification, variables: {userId: theirUserId}})
    .subscribe({
      next: (resp) => msgNotifications.push(resp),
      error: (resp) => console.log(resp),
    })

  // they open up a chat with us
  const [chatId, messageId1] = [uuidv4(), uuidv4()]
  await theirClient
    .mutate({
      mutation: mutations.createDirectChat,
      variables: {userId: ourUserId, chatId, messageId: messageId1, messageText: 'hey, msg1'},
    })
    .then(({data: {createDirectChat: chat}}) => {
      expect(chat.chatId).toBe(chatId)
      expect(chat.messages.items).toHaveLength(1)
      expect(chat.messages.items[0].messageId).toBe(messageId1)
    })

  // we send a messsage to the chat
  await ourClient
    .mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: uuidv4(), text: 'lore'}})
    .then(({data: {addChatMessage: message}}) => expect(message.chat.chatId).toBe(chatId))

  // they send a messsage to the chat
  await theirClient
    .mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: uuidv4(), text: 'ipsum'}})
    .then(({data: {addChatMessage: message}}) => expect(message.chat.chatId).toBe(chatId))

  // wait for some messages to show up, ensure none did
  await misc.sleep(5000)
  expect(msgNotifications).toEqual([])

  // we don't unsubscribe from the subscription because
  //  - it's not actually active, although I have yet to find a way to expect() that
  //  - unsubcribing results in the AWS SDK throwing errors
})

test('Messages in multiple chats fire', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()
  const {client: otherClient, userId: otherUserId} = await loginCache.getCleanLogin()

  // we subscribe to chat messages
  const ourMsgNotifications = []
  const ourSub = await ourClient
    .subscribe({query: subscriptions.onChatMessageNotification, variables: {userId: ourUserId}})
    .subscribe({next: ({data}) => ourMsgNotifications.push(data.onChatMessageNotification)})
  const ourSubInitTimeout = misc.sleep(15000) // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541

  // they subscribe to chat messages
  const theirMsgNotifications = []
  const theirSub = await theirClient
    .subscribe({query: subscriptions.onChatMessageNotification, variables: {userId: theirUserId}})
    .subscribe({next: ({data}) => theirMsgNotifications.push(data.onChatMessageNotification)})
  const theirSubInitTimeout = misc.sleep(15000) // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541

  // other subscribes to chat messages
  const otherMsgNotifications = []
  const otherSub = await otherClient
    .subscribe({query: subscriptions.onChatMessageNotification, variables: {userId: otherUserId}})
    .subscribe({next: ({data}) => otherMsgNotifications.push(data.onChatMessageNotification)})
  const otherSubInitTimeout = misc.sleep(15000) // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541

  // we open a direct chat with them
  await misc.sleep(2000) // let the subscriptions initialize
  const [chatId, messageId1] = [uuidv4(), uuidv4()]
  await ourClient
    .mutate({
      mutation: mutations.createDirectChat,
      variables: {userId: theirUserId, chatId, messageId: messageId1, messageText: 'm1'},
    })
    .then(({data}) => {
      expect(data.createDirectChat.chatId).toBe(chatId)
      expect(data.createDirectChat.messages.items).toHaveLength(1)
      expect(data.createDirectChat.messages.items[0].messageId).toBe(messageId1)
    })

  // they post a message to the chat
  await misc.sleep(1000) // notification ordering
  const messageId2 = uuidv4()
  await theirClient
    .mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: messageId2, text: 'm2'}})
    .then(({data}) => {
      expect(data.addChatMessage.chat.chatId).toBe(chatId)
      expect(data.addChatMessage.messageId).toBe(messageId2)
    })

  // other opens a group chat with all three of us
  await misc.sleep(1000) // notification ordering
  const [chatId2, messageId3] = [uuidv4(), uuidv4()]
  await otherClient
    .mutate({
      mutation: mutations.createGroupChat,
      variables: {chatId: chatId2, userIds: [ourUserId, theirUserId], messageId: messageId3, messageText: 'm3'},
    })
    .then(({data}) => expect(data.createGroupChat.chatId).toBe(chatId2))

  // we post a message to the group chat
  await misc.sleep(1000) // notification ordering
  const messageId4 = uuidv4()
  await ourClient
    .mutate({
      mutation: mutations.addChatMessage,
      variables: {chatId: chatId2, messageId: messageId4, text: 'm4'},
    })
    .then(({data}) => {
      expect(data.addChatMessage.chat.chatId).toBe(chatId2)
      expect(data.addChatMessage.messageId).toBe(messageId4)
    })

  // give all notifications a moment to show up
  await misc.sleep(6000)

  /* Use me to establish order among notifications */
  const notificationCompare = (a, b) => {
    const aTextReversed = a.message.text.split('').reverse().join('')
    const bTextReversed = b.message.text.split('').reverse().join('')
    return aTextReversed.localeCompare(bTextReversed)
  }

  // we should see all messages from chats we were in (except our own messages), order not guaranteed
  ourMsgNotifications.sort(notificationCompare)
  expect(ourMsgNotifications).toHaveLength(3)
  expect(ourMsgNotifications[0].message.messageId).toBe(messageId2)
  expect(ourMsgNotifications[0].message.authorUserId).toBe(theirUserId)
  expect(ourMsgNotifications[1].message.messageId).toBe(messageId3)
  expect(ourMsgNotifications[1].message.authorUserId).toBe(otherUserId)
  expect(ourMsgNotifications[2].message.text).toContain('added')
  expect(ourMsgNotifications[2].message.authorUserId).toBeNull()

  // they should see all messages from chats they were in (except their own messages), order not guaranteed
  theirMsgNotifications.sort(notificationCompare)
  expect(theirMsgNotifications).toHaveLength(4)
  expect(theirMsgNotifications[0].message.messageId).toBe(messageId1)
  expect(theirMsgNotifications[0].message.authorUserId).toBe(ourUserId)
  expect(theirMsgNotifications[1].message.messageId).toBe(messageId3)
  expect(theirMsgNotifications[1].message.authorUserId).toBe(otherUserId)
  expect(theirMsgNotifications[2].message.messageId).toBe(messageId4)
  expect(theirMsgNotifications[2].message.authorUserId).toBe(ourUserId)
  expect(theirMsgNotifications[3].message.text).toContain('added')
  expect(theirMsgNotifications[3].message.authorUserId).toBeNull()

  // other should see all messages from their chats (except their own), order not guaranteed
  otherMsgNotifications.sort(notificationCompare)
  expect(otherMsgNotifications).toHaveLength(3)
  expect(otherMsgNotifications[0].message.messageId).toBe(messageId4)
  expect(otherMsgNotifications[0].message.authorUserId).toBe(ourUserId)
  expect(otherMsgNotifications[1].message.text).toContain('created')
  expect(otherMsgNotifications[1].message.authorUserId).toBeNull()
  expect(otherMsgNotifications[2].message.text).toContain('added')
  expect(otherMsgNotifications[2].message.authorUserId).toBeNull()

  // shut down the subscriptions
  ourSub.unsubscribe()
  theirSub.unsubscribe()
  otherSub.unsubscribe()
  await ourSubInitTimeout
  await theirSubInitTimeout
  await otherSubInitTimeout
})

test('Format for ADDED, EDITED, DELETED message notifications', async () => {
  const {client: ourClient, userId: ourUserId, username: ourUsername} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId, username: theirUsername} = await loginCache.getCleanLogin()

  // they open up a chat with us
  const [chatId, messageId1] = [uuidv4(), uuidv4()]
  await theirClient
    .mutate({
      mutation: mutations.createDirectChat,
      variables: {userId: ourUserId, chatId, messageId: messageId1, messageText: 'hey m1'},
    })
    .then(({data: {createDirectChat: chat}}) => {
      expect(chat.chatId).toBe(chatId)
      expect(chat.messages.items).toHaveLength(1)
      expect(chat.messages.items[0].messageId).toBe(messageId1)
    })

  // state that will allow us to create promises that resolve to the next notification from the subscription
  const [resolvers, rejectors] = [[], []]

  // set up a promise that will resolve to the first message received from the subscription
  let nextNotification = new Promise((resolve, reject) => {
    resolvers.push(resolve)
    rejectors.push(reject)
  })
  const sub = await ourClient
    .subscribe({query: subscriptions.onChatMessageNotification, variables: {userId: ourUserId}})
    .subscribe({
      next: (resp) => {
        rejectors.pop()
        resolvers.pop()(resp)
      },
      error: (resp) => {
        resolvers.pop()
        rejectors.pop()(resp)
      },
    })
  const subInitTimeout = misc.sleep(15000) // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541
  await misc.sleep(2000) // let the subscription initialize

  // they add a message to the chat
  const [messageId2, text2] = [uuidv4(), `hi @${ourUsername}!`]
  const createdAt = await theirClient
    .mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: messageId2, text: text2}})
    .then(({data: {addChatMessage: message}}) => {
      expect(message.messageId).toBe(messageId2)
      expect(message.chat.chatId).toBe(chatId)
      expect(message.createdAt).toBeTruthy()
      return message.createdAt
    })

  // verify the subscription received the notification and in correct format
  await nextNotification.then(({data: {onChatMessageNotification}}) => {
    expect(onChatMessageNotification.userId).toBe(ourUserId)
    expect(onChatMessageNotification.type).toBe('ADDED')
    expect(onChatMessageNotification.message.messageId).toBe(messageId2)
    expect(onChatMessageNotification.message.chat.chatId).toBe(chatId)
    expect(onChatMessageNotification.message.authorUserId).toBe(theirUserId)
    expect(onChatMessageNotification.message.author.userId).toBe(theirUserId)
    expect(onChatMessageNotification.message.author.username).toBe(theirUsername)
    expect(onChatMessageNotification.message.author.photo).toBeNull()
    expect(onChatMessageNotification.message.text).toBe(text2)
    expect(onChatMessageNotification.message.textTaggedUsers).toHaveLength(1)
    expect(onChatMessageNotification.message.textTaggedUsers[0].tag).toBe(`@${ourUsername}`)
    expect(onChatMessageNotification.message.textTaggedUsers[0].user.userId).toBe(ourUserId)
    expect(onChatMessageNotification.message.createdAt).toBe(createdAt)
    expect(onChatMessageNotification.message.lastEditedAt).toBeNull()
  })

  // they add a post they will use as a profile photo
  const postId = uuidv4()
  await theirClient
    .mutate({mutation: mutations.addPost, variables: {postId, imageData: grantDataB64, takenInReal: true}})
    .then(({data: {addPost: post}}) => expect(post.postId).toBe(postId))

  // they set that post as their profile photo
  await theirClient
    .mutate({mutation: mutations.setUserDetails, variables: {photoPostId: postId}})
    .then(({data: {setUserDetails: user}}) => expect(user.photo.url).toBeTruthy())

  // set up a promise for the next notification
  nextNotification = new Promise((resolve, reject) => {
    resolvers.push(resolve)
    rejectors.push(reject)
  })

  // they edit their message to the chat
  const text3 = `this is @${theirUsername}!`
  const lastEditedAt = await theirClient
    .mutate({mutation: mutations.editChatMessage, variables: {messageId: messageId2, text: text3}})
    .then(({data: {editChatMessage: message}}) => {
      expect(message.messageId).toBe(messageId2)
      expect(message.text).toBe(text3)
      expect(message.lastEditedAt).toBeTruthy()
      return message.lastEditedAt
    })

  // verify the subscription received the notification and in correct format
  await nextNotification.then(({data: {onChatMessageNotification}}) => {
    expect(onChatMessageNotification.userId).toBe(ourUserId)
    expect(onChatMessageNotification.type).toBe('EDITED')
    expect(onChatMessageNotification.message.messageId).toBe(messageId2)
    expect(onChatMessageNotification.message.chat.chatId).toBe(chatId)
    expect(onChatMessageNotification.message.authorUserId).toBe(theirUserId)
    expect(onChatMessageNotification.message.author.userId).toBe(theirUserId)
    expect(onChatMessageNotification.message.author.username).toBe(theirUsername)
    expect(onChatMessageNotification.message.author.photo.url64p).toBeTruthy()
    expect(onChatMessageNotification.message.text).toBe(text3)
    expect(onChatMessageNotification.message.textTaggedUsers).toHaveLength(1)
    expect(onChatMessageNotification.message.textTaggedUsers[0].tag).toBe(`@${theirUsername}`)
    expect(onChatMessageNotification.message.textTaggedUsers[0].user.userId).toBe(theirUserId)
    expect(onChatMessageNotification.message.createdAt).toBe(createdAt)
    expect(onChatMessageNotification.message.lastEditedAt).toBe(lastEditedAt)
  })

  // set up a promise for the next notification
  nextNotification = new Promise((resolve, reject) => {
    resolvers.push(resolve)
    rejectors.push(reject)
  })

  // they delete their message to the chat
  await theirClient
    .mutate({mutation: mutations.deleteChatMessage, variables: {messageId: messageId2}})
    .then(({data: {deleteChatMessage: message}}) => expect(message.messageId).toBe(messageId2))

  // verify the subscription received the notificaiton and in correct format
  await nextNotification.then(({data: {onChatMessageNotification}}) => {
    expect(onChatMessageNotification.userId).toBe(ourUserId)
    expect(onChatMessageNotification.type).toBe('DELETED')
    expect(onChatMessageNotification.message.messageId).toBe(messageId2)
    expect(onChatMessageNotification.message.chat.chatId).toBe(chatId)
    expect(onChatMessageNotification.message.authorUserId).toBe(theirUserId)
    expect(onChatMessageNotification.message.author.userId).toBe(theirUserId)
    expect(onChatMessageNotification.message.author.username).toBe(theirUsername)
    expect(onChatMessageNotification.message.author.photo.url64p).toBeTruthy()
    expect(onChatMessageNotification.message.text).toBe(text3)
    expect(onChatMessageNotification.message.textTaggedUsers).toHaveLength(1)
    expect(onChatMessageNotification.message.textTaggedUsers[0].tag).toBe(`@${theirUsername}`)
    expect(onChatMessageNotification.message.textTaggedUsers[0].user.userId).toBe(theirUserId)
    expect(onChatMessageNotification.message.createdAt).toBe(createdAt)
    expect(onChatMessageNotification.message.lastEditedAt).toBe(lastEditedAt)
  })

  // shut down the subscription
  sub.unsubscribe()
  await subInitTimeout
})

test('Notifications for a group chat', async () => {
  const {client: ourClient, userId: ourUserId, username: ourUsername} = await loginCache.getCleanLogin()
  const {client: other1Client, userId: other1UserId} = await loginCache.getCleanLogin()
  const {client: other2Client, userId: other2UserId} = await loginCache.getCleanLogin()

  // we create a group chat with all of us in it
  const chatId = uuidv4()
  await ourClient
    .mutate({
      mutation: mutations.createGroupChat,
      variables: {chatId, userIds: [other1UserId, other2UserId], messageId: uuidv4(), messageText: 'm1'},
    })
    .then(({data: {createGroupChat: chat}}) => expect(chat.chatId).toBe(chatId))

  // we initialize a subscription to new message notifications
  const [resolvers, rejectors] = [[], []]
  let nextNotification = new Promise((resolve, reject) => {
    resolvers.push(resolve)
    rejectors.push(reject)
  })
  const sub = await ourClient
    .subscribe({query: subscriptions.onChatMessageNotification, variables: {userId: ourUserId}})
    .subscribe({
      next: (resp) => {
        rejectors.pop()
        resolvers.pop()(resp)
      },
      error: (resp) => {
        resolvers.pop()
        rejectors.pop()(resp)
      },
    })
  const subInitTimeout = misc.sleep(15000) // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541
  await misc.sleep(2000) // let the subscription initialize

  // other1 adds a message to the chat
  const messageId2 = uuidv4()
  await other1Client
    .mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: messageId2, text: 'text 2'}})
    .then(({data: {addChatMessage: message}}) => expect(message.messageId).toBe(messageId2))

  // verify we received the message
  await nextNotification.then(({data: {onChatMessageNotification}}) => {
    expect(onChatMessageNotification.message.messageId).toBe(messageId2)
    expect(onChatMessageNotification.message.authorUserId).toBe(other1UserId)
  })
  nextNotification = new Promise((resolve, reject) => {
    resolvers.push(resolve)
    rejectors.push(reject)
  })

  // we edit group name to trigger a system message
  await ourClient
    .mutate({mutation: mutations.editGroupChat, variables: {chatId, name: 'new name'}})
    .then(({data: {editGroupChat: chat}}) => {
      expect(chat.chatId).toBe(chatId)
      expect(chat.name).toBe('new name')
    })

  // verify we received the message
  await nextNotification.then(({data: {onChatMessageNotification}}) => {
    expect(onChatMessageNotification.message.messageId).toBeTruthy()
    expect(onChatMessageNotification.message.text).toContain(ourUsername)
    expect(onChatMessageNotification.message.text).toContain('changed the name of the group')
    expect(onChatMessageNotification.message.text).toContain('"new name"')
    expect(onChatMessageNotification.message.textTaggedUsers).toHaveLength(1)
    expect(onChatMessageNotification.message.textTaggedUsers[0].tag).toContain(ourUsername)
    expect(onChatMessageNotification.message.textTaggedUsers[0].user.userId).toContain(ourUserId)
    expect(onChatMessageNotification.message.authorUserId).toBeNull()
    expect(onChatMessageNotification.message.author).toBeNull()
  })
  nextNotification = new Promise((resolve, reject) => {
    resolvers.push(resolve)
    rejectors.push(reject)
  })

  // other2 adds a message to the chat
  const messageId3 = uuidv4()
  await other2Client
    .mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: messageId3, text: 'text 3'}})
    .then(({data: {addChatMessage: message}}) => expect(message.messageId).toBe(messageId3))

  // verify we received the message
  await nextNotification.then(({data: {onChatMessageNotification}}) => {
    expect(onChatMessageNotification.message.messageId).toBe(messageId3)
    expect(onChatMessageNotification.message.authorUserId).toBe(other2UserId)
  })

  // shut down our subscription
  sub.unsubscribe()
  await subInitTimeout
})

test('Message notifications from blocke[r|d] users have authorUserId but no author', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // we create a group chat with both of us in it
  const chatId = uuidv4()
  await ourClient
    .mutate({
      mutation: mutations.createGroupChat,
      variables: {chatId, userIds: [theirUserId], messageId: uuidv4(), messageText: 'm1'},
    })
    .then(({data: {createGroupChat: chat}}) => {
      expect(chat.chatId).toBe(chatId)
      expect(chat.userCount).toBe(2)
      expect(chat.usersCount).toBe(2)
      expect(chat.users.items.map((u) => u.userId).sort()).toEqual([ourUserId, theirUserId].sort())
    })

  // they block us
  await theirClient
    .mutate({mutation: mutations.blockUser, variables: {userId: ourUserId}})
    .then(({data: {blockUser: user}}) => {
      expect(user.userId).toBe(ourUserId)
      expect(user.blockedStatus).toBe('BLOCKING')
    })

  // they listen to message notifciations
  let next, error
  const theirNextNotification = new Promise((resolve, reject) => {
    next = resolve
    error = reject
  })
  const theirSub = await theirClient
    .subscribe({query: subscriptions.onChatMessageNotification, variables: {userId: theirUserId}})
    .subscribe({next, error})
  const theirSubInitTimeout = misc.sleep(15000) // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541
  await misc.sleep(2000) // let the subscription initialize

  // we add a message
  const messageId2 = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: messageId2, text: 'lore'}})
    .then(({data: {addChatMessage: message}}) => expect(message.messageId).toBe(messageId2))

  // verify they received a notifcation for our message with no author
  await theirNextNotification.then(({data: {onChatMessageNotification}}) => {
    expect(onChatMessageNotification.message.messageId).toBe(messageId2)
    expect(onChatMessageNotification.message.authorUserId).toBe(ourUserId)
    expect(onChatMessageNotification.message.author).toBeNull()
  })

  // we listen to notifciations
  const ourNextNotification = new Promise((resolve, reject) => {
    next = resolve
    error = reject
  })
  const ourSub = await ourClient
    .subscribe({query: subscriptions.onChatMessageNotification, variables: {userId: ourUserId}})
    .subscribe({next, error})
  const ourSubInitTimeout = misc.sleep(15000) // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541
  await misc.sleep(2000) // let the subscription initialize

  // they add a message
  const messageId3 = uuidv4()
  await theirClient
    .mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: messageId3, text: 'ipsum'}})
    .then(({data: {addChatMessage: chat}}) => expect(chat.messageId).toBe(messageId3))

  // verify we received a notifcation for their message
  await ourNextNotification.then(({data: {onChatMessageNotification}}) => {
    expect(onChatMessageNotification.message.messageId).toBe(messageId3)
    expect(onChatMessageNotification.message.authorUserId).toBe(theirUserId)
    expect(onChatMessageNotification.message.author).toBeNull()
  })

  // shut down the subscriptions
  ourSub.unsubscribe()
  theirSub.unsubscribe()
  await ourSubInitTimeout
  await theirSubInitTimeout
})
