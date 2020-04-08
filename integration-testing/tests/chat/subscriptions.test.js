/* eslint-env jest */

const fs = require('fs')
const moment = require('moment')
const path = require('path')
const uuidv4 = require('uuid/v4')
// the aws-appsync-subscription-link pacakge expects WebSocket to be globaly defined, like in the browser
global.WebSocket = require('ws')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const schema = require('../../utils/schema.js')

const grantData = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg'))
const grantDataB64 = new Buffer.from(grantData).toString('base64')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Chat message triggers cannot be called from external graphql client', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // they open up a chat with us
  const [chatId, messageId] = [uuidv4(), uuidv4()]
  let variables = {userId: ourUserId, chatId, messageId, messageText: 'lore ipsum'}
  let resp = await theirClient.mutate({mutation: schema.createDirectChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createDirectChat']['chatId']).toBe(chatId)
  expect(resp['data']['createDirectChat']['messages']['items']).toHaveLength(1)
  expect(resp['data']['createDirectChat']['messages']['items'][0]['messageId']).toBe(messageId)

  // create a well-formed valid chat notification object
  variables = {input: {
    userId: ourUserId,
    messageId,
    chatId,
    authorUserId: ourUserId,
    type: 'ADDED',
    text: 'lore ipsum',
    textTaggedUserIds: [],
    createdAt: moment().toISOString(),
  }}

  // verify niether of us can call the trigger method, even with a valid chat & message id
  let mutation = schema.triggerChatMessageNotification
  await expect(ourClient.mutate({mutation, variables})).rejects.toThrow('ClientError')
  await expect(theirClient.mutate({mutation, variables})).rejects.toThrow('ClientError')
})


test('Cannot subscribe to other users messages', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // verify we cannot subscribe to their messages
  // Note: there doesn't seem to be any error thrown at the time of subscription, it's just that
  // the subscription next() method is never triggered
  const msgNotifications = []
  await ourClient
    .subscribe({query: schema.onChatMessageNotification, variables: {userId: theirUserId}})
    .subscribe({next: resp => { msgNotifications.push(resp) }, error: resp => { console.log(resp) }})

  // they open up a chat with us
  const [chatId, messageId1, text1] = [uuidv4(), uuidv4(), 'hey this is msg 1']
  let variables = {userId: ourUserId, chatId, messageId: messageId1, messageText: text1}
  let resp = await theirClient.mutate({mutation: schema.createDirectChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createDirectChat']['chatId']).toBe(chatId)
  expect(resp['data']['createDirectChat']['messages']['items']).toHaveLength(1)
  expect(resp['data']['createDirectChat']['messages']['items'][0]['messageId']).toBe(messageId1)

  // we send a messsage to the chat
  variables = {chatId, messageId: uuidv4() , text: 'lore'}
  resp = await ourClient.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['chat']['chatId']).toBe(chatId)

  // they send a messsage to the chat
  variables = {chatId, messageId: uuidv4() , text: 'ipsum'}
  resp = await theirClient.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['chat']['chatId']).toBe(chatId)

  // wait for some messages to show up, ensure none did
  await misc.sleep(5000)
  expect(msgNotifications).toEqual([])

  // we don't unsubscribe from the subscription because
  //  - it's not actually active, although I have yet to find a way to expect() that
  //  - unsubcribing results in the AWS SDK throwing errors
})


test('Messages in multiple chats fire', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()
  const [otherClient, otherUserId] = await loginCache.getCleanLogin()

  // we subscribe to chat messages
  const ourMsgNotifications = []
  const ourSub = await ourClient
    .subscribe({query: schema.onChatMessageNotification, variables: {userId: ourUserId}})
    .subscribe({next: resp => { ourMsgNotifications.push(resp) }})
  const ourSubInitTimeout = misc.sleep(15000)  // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541

  // they subscribe to chat messages
  const theirMsgNotifications = []
  const theirSub = await theirClient
    .subscribe({query: schema.onChatMessageNotification, variables: {userId: theirUserId}})
    .subscribe({next: resp => { theirMsgNotifications.push(resp) }})
  const theirSubInitTimeout = misc.sleep(15000)  // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541

  // other subscribes to chat messages
  const otherMsgNotifications = []
  const otherSub = await otherClient
    .subscribe({query: schema.onChatMessageNotification, variables: {userId: otherUserId}})
    .subscribe({next: resp => { otherMsgNotifications.push(resp) }})
  const otherSubInitTimeout = misc.sleep(15000)  // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541
  await misc.sleep(2000)  // let the subscription initialize

  // we open a direct chat with them
  const [chatId, messageId1] = [uuidv4(), uuidv4()]
  let variables = {userId: theirUserId, chatId, messageId: messageId1, messageText: 'msg 1'}
  let resp = await ourClient.mutate({mutation: schema.createDirectChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createDirectChat']['chatId']).toBe(chatId)
  expect(resp['data']['createDirectChat']['messages']['items']).toHaveLength(1)
  expect(resp['data']['createDirectChat']['messages']['items'][0]['messageId']).toBe(messageId1)

  // they post a message to the chat
  const messageId2 = uuidv4()
  variables = {chatId, messageId: messageId2, text: 'msg 2'}
  resp = await theirClient.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId2)
  expect(resp['data']['addChatMessage']['chat']['chatId']).toBe(chatId)

  // other opens a group chat with all three of us
  const [chatId2, messageId3] = [uuidv4(), uuidv4()]
  variables = {chatId: chatId2, userIds: [ourUserId, theirUserId], messageId: messageId3, messageText: 'msg 3'}
  resp = await otherClient.mutate({mutation: schema.createGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createGroupChat']['chatId']).toBe(chatId2)

  // we post a message to the group chat
  const messageId4 = uuidv4()
  variables = {chatId: chatId2, messageId: messageId4, text: 'msg 4'}
  resp = await ourClient.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId4)
  expect(resp['data']['addChatMessage']['chat']['chatId']).toBe(chatId2)

  // give final notifications a moment to show up
  await misc.sleep(2000)

  // we should see all messages from chats we were in (except our own messages)
  expect(ourMsgNotifications).toHaveLength(3)
  expect(ourMsgNotifications[0]['data']['onChatMessageNotification']['message']['authorUserId']).toBe(theirUserId)
  expect(ourMsgNotifications[1]['data']['onChatMessageNotification']['message']['authorUserId']).toBeNull()
  expect(ourMsgNotifications[2]['data']['onChatMessageNotification']['message']['authorUserId']).toBe(otherUserId)

  expect(ourMsgNotifications[0]['data']['onChatMessageNotification']['message']['messageId']).toBe(messageId2)
  expect(ourMsgNotifications[1]['data']['onChatMessageNotification']['message']['text']).toContain('added')
  expect(ourMsgNotifications[2]['data']['onChatMessageNotification']['message']['messageId']).toBe(messageId3)

  // they should see all messages from chats they were in (except their own messages)
  expect(theirMsgNotifications).toHaveLength(4)
  expect(theirMsgNotifications[0]['data']['onChatMessageNotification']['message']['authorUserId']).toBe(ourUserId)
  expect(theirMsgNotifications[1]['data']['onChatMessageNotification']['message']['authorUserId']).toBeNull()
  expect(theirMsgNotifications[2]['data']['onChatMessageNotification']['message']['authorUserId']).toBe(otherUserId)
  expect(theirMsgNotifications[3]['data']['onChatMessageNotification']['message']['authorUserId']).toBe(ourUserId)

  expect(theirMsgNotifications[0]['data']['onChatMessageNotification']['message']['messageId']).toBe(messageId1)
  expect(theirMsgNotifications[1]['data']['onChatMessageNotification']['message']['text']).toContain('added')
  expect(theirMsgNotifications[2]['data']['onChatMessageNotification']['message']['messageId']).toBe(messageId3)
  expect(theirMsgNotifications[3]['data']['onChatMessageNotification']['message']['messageId']).toBe(messageId4)

  // other should see all msg from their chats (except their own)
  expect(otherMsgNotifications).toHaveLength(3)
  expect(otherMsgNotifications[0]['data']['onChatMessageNotification']['message']['authorUserId']).toBeNull()
  expect(otherMsgNotifications[1]['data']['onChatMessageNotification']['message']['authorUserId']).toBeNull()
  expect(otherMsgNotifications[2]['data']['onChatMessageNotification']['message']['authorUserId']).toBe(ourUserId)

  expect(otherMsgNotifications[0]['data']['onChatMessageNotification']['message']['text']).toContain('created')
  expect(otherMsgNotifications[1]['data']['onChatMessageNotification']['message']['text']).toContain('added')
  expect(otherMsgNotifications[2]['data']['onChatMessageNotification']['message']['messageId']).toBe(messageId4)

  // shut down the subscriptions
  ourSub.unsubscribe()
  theirSub.unsubscribe()
  otherSub.unsubscribe()
  await ourSubInitTimeout
  await theirSubInitTimeout
  await otherSubInitTimeout
})


test('Format for ADDED, EDITED, DELETED message notifications', async () => {
  const [ourClient, ourUserId, , , ourUsername] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId, , , theirUsername] = await loginCache.getCleanLogin()

  // they open up a chat with us
  const [chatId, messageId1, text1] = [uuidv4(), uuidv4(), 'hey this is msg 1']
  let variables = {userId: ourUserId, chatId, messageId: messageId1, messageText: text1}
  let resp = await theirClient.mutate({mutation: schema.createDirectChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createDirectChat']['chatId']).toBe(chatId)
  expect(resp['data']['createDirectChat']['messages']['items']).toHaveLength(1)
  expect(resp['data']['createDirectChat']['messages']['items'][0]['messageId']).toBe(messageId1)

  // state that will allow us to create promises that resolve to the next notification from the subscription
  const [resolvers, rejectors] = [[], []]

  // set up a promise that will resolve to the first message received from the subscription
  let nextNotification = new Promise((resolve, reject) => {resolvers.push(resolve); rejectors.push(reject)})
  const sub = await ourClient
    .subscribe({query: schema.onChatMessageNotification, variables: {userId: ourUserId}})
    .subscribe({
      next: resp => { rejectors.pop(); resolvers.pop()(resp) },
      error: resp => { resolvers.pop(); rejectors.pop()(resp) },
    })
  const subInitTimeout = misc.sleep(15000)  // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541
  await misc.sleep(2000)  // let the subscription initialize

  // they add a message to the chat
  const [messageId2, text2] = [uuidv4(), `hi @${ourUsername}!`]
  variables = {chatId, messageId: messageId2, text: text2}
  resp = await theirClient.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId2)
  expect(resp['data']['addChatMessage']['chat']['chatId']).toBe(chatId)
  const createdAt = resp['data']['addChatMessage']['createdAt']
  expect(createdAt).toBeTruthy()

  // verify the subscription received the notification and in correct format
  resp = await nextNotification
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['onChatMessageNotification']['userId']).toBe(ourUserId)
  expect(resp['data']['onChatMessageNotification']['type']).toBe('ADDED')
  expect(resp['data']['onChatMessageNotification']['message']['messageId']).toBe(messageId2)
  expect(resp['data']['onChatMessageNotification']['message']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['onChatMessageNotification']['message']['authorUserId']).toBe(theirUserId)
  expect(resp['data']['onChatMessageNotification']['message']['author']['userId']).toBe(theirUserId)
  expect(resp['data']['onChatMessageNotification']['message']['author']['username']).toBe(theirUsername)
  expect(resp['data']['onChatMessageNotification']['message']['author']['photo']).toBeNull()
  expect(resp['data']['onChatMessageNotification']['message']['text']).toBe(text2)
  expect(resp['data']['onChatMessageNotification']['message']['textTaggedUsers']).toHaveLength(1)
  expect(resp['data']['onChatMessageNotification']['message']['textTaggedUsers'][0]['tag']).toBe(`@${ourUsername}`)
  expect(resp['data']['onChatMessageNotification']['message']['textTaggedUsers'][0]['user']['userId'])
    .toBe(ourUserId)
  expect(resp['data']['onChatMessageNotification']['message']['createdAt']).toBe(createdAt)
  expect(resp['data']['onChatMessageNotification']['message']['lastEditedAt']).toBeNull()

  // they add a post they will use as a profile photo
  const postId = uuidv4()
  resp = await theirClient.mutate({mutation: schema.addPost, variables: {postId, imageData: grantDataB64}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // they set that post as their profile photo
  resp = await theirClient.mutate({mutation: schema.setUserDetails, variables: {photoPostId: postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['photo']['url']).toBeTruthy()

  // set up a promise for the next notification
  nextNotification = new Promise((resolve, reject) => {resolvers.push(resolve); rejectors.push(reject)})

  // they edit their message to the chat
  const text3 = `this is @${theirUsername}!`
  variables = {messageId: messageId2, text: text3}
  resp = await theirClient.mutate({mutation: schema.editChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editChatMessage']['messageId']).toBe(messageId2)
  expect(resp['data']['editChatMessage']['text']).toBe(text3)
  const lastEditedAt = resp['data']['editChatMessage']['lastEditedAt']
  expect(lastEditedAt).toBeTruthy()

  // verify the subscription received the notification and in correct format
  resp = await nextNotification
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['onChatMessageNotification']['userId']).toBe(ourUserId)
  expect(resp['data']['onChatMessageNotification']['type']).toBe('EDITED')
  expect(resp['data']['onChatMessageNotification']['message']['messageId']).toBe(messageId2)
  expect(resp['data']['onChatMessageNotification']['message']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['onChatMessageNotification']['message']['authorUserId']).toBe(theirUserId)
  expect(resp['data']['onChatMessageNotification']['message']['author']['userId']).toBe(theirUserId)
  expect(resp['data']['onChatMessageNotification']['message']['author']['username']).toBe(theirUsername)
  expect(resp['data']['onChatMessageNotification']['message']['author']['photo']['url64p']).toBeTruthy()
  expect(resp['data']['onChatMessageNotification']['message']['text']).toBe(text3)
  expect(resp['data']['onChatMessageNotification']['message']['textTaggedUsers']).toHaveLength(1)
  expect(resp['data']['onChatMessageNotification']['message']['textTaggedUsers'][0]['tag']).toBe(`@${theirUsername}`)
  expect(resp['data']['onChatMessageNotification']['message']['textTaggedUsers'][0]['user']['userId'])
    .toBe(theirUserId)
  expect(resp['data']['onChatMessageNotification']['message']['createdAt']).toBe(createdAt)
  expect(resp['data']['onChatMessageNotification']['message']['lastEditedAt']).toBe(lastEditedAt)

  // set up a promise for the next notification
  nextNotification = new Promise((resolve, reject) => {resolvers.push(resolve); rejectors.push(reject)})

  // they delete their message to the chat
  variables = {messageId: messageId2}
  resp = await theirClient.mutate({mutation: schema.deleteChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['deleteChatMessage']['messageId']).toBe(messageId2)

  // verify the subscription received the notificaiton and in correct format
  resp = await nextNotification
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['onChatMessageNotification']['userId']).toBe(ourUserId)
  expect(resp['data']['onChatMessageNotification']['type']).toBe('DELETED')
  expect(resp['data']['onChatMessageNotification']['message']['messageId']).toBe(messageId2)
  expect(resp['data']['onChatMessageNotification']['message']['chat']['chatId']).toBe(chatId)
  expect(resp['data']['onChatMessageNotification']['message']['authorUserId']).toBe(theirUserId)
  expect(resp['data']['onChatMessageNotification']['message']['author']['userId']).toBe(theirUserId)
  expect(resp['data']['onChatMessageNotification']['message']['author']['username']).toBe(theirUsername)
  expect(resp['data']['onChatMessageNotification']['message']['author']['photo']['url64p']).toBeTruthy()
  expect(resp['data']['onChatMessageNotification']['message']['text']).toBe(text3)
  expect(resp['data']['onChatMessageNotification']['message']['textTaggedUsers']).toHaveLength(1)
  expect(resp['data']['onChatMessageNotification']['message']['textTaggedUsers'][0]['tag']).toBe(`@${theirUsername}`)
  expect(resp['data']['onChatMessageNotification']['message']['textTaggedUsers'][0]['user']['userId'])
    .toBe(theirUserId)
  expect(resp['data']['onChatMessageNotification']['message']['createdAt']).toBe(createdAt)
  expect(resp['data']['onChatMessageNotification']['message']['lastEditedAt']).toBe(lastEditedAt)

  // shut down the subscription
  sub.unsubscribe()
  await subInitTimeout
})


test('Notifications for a group chat', async () => {
  const [ourClient, ourUserId, , , ourUsername] = await loginCache.getCleanLogin()
  const [other1Client, other1UserId] = await loginCache.getCleanLogin()
  const [other2Client, other2UserId] = await loginCache.getCleanLogin()

  // we create a group chat with all of us in it
  const chatId = uuidv4()
  let variables = {chatId, userIds: [other1UserId, other2UserId], messageId: uuidv4(), messageText: 'm1'}
  let resp = await ourClient.mutate({mutation: schema.createGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createGroupChat']['chatId']).toBe(chatId)

  // we initialize a subscription to new message notifications
  const [resolvers, rejectors] = [[], []]
  let nextNotification = new Promise((resolve, reject) => {resolvers.push(resolve); rejectors.push(reject)})
  const sub = await ourClient
    .subscribe({query: schema.onChatMessageNotification, variables: {userId: ourUserId}})
    .subscribe({
      next: resp => { rejectors.pop(); resolvers.pop()(resp) },
      error: resp => { resolvers.pop(); rejectors.pop()(resp) },
    })
  const subInitTimeout = misc.sleep(15000)  // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541
  await misc.sleep(2000)  // let the subscription initialize

  // other1 adds a message to the chat
  const messageId2 = uuidv4()
  variables = {chatId, messageId: messageId2, text: 'text 2'}
  resp = await other1Client.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId2)

  // verify we received the message
  resp = await nextNotification
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['onChatMessageNotification']['message']['messageId']).toBe(messageId2)
  expect(resp['data']['onChatMessageNotification']['message']['authorUserId']).toBe(other1UserId)
  nextNotification = new Promise((resolve, reject) => {resolvers.push(resolve); rejectors.push(reject)})

  // we edit group name to trigger a system message
  variables = {chatId, name: 'new name'}
  resp = await ourClient.mutate({mutation: schema.editGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editGroupChat']['chatId']).toBe(chatId)
  expect(resp['data']['editGroupChat']['name']).toBe('new name')

  // verify we received the message
  resp = await nextNotification
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['onChatMessageNotification']['message']['messageId']).toBeTruthy()
  expect(resp['data']['onChatMessageNotification']['message']['text']).toContain(ourUsername)
  expect(resp['data']['onChatMessageNotification']['message']['text']).toContain('changed the name of the group')
  expect(resp['data']['onChatMessageNotification']['message']['text']).toContain('"new name"')
  expect(resp['data']['onChatMessageNotification']['message']['textTaggedUsers']).toHaveLength(1)
  expect(resp['data']['onChatMessageNotification']['message']['textTaggedUsers'][0]['tag']).toContain(ourUsername)
  expect(resp['data']['onChatMessageNotification']['message']['textTaggedUsers'][0]['user']['userId'])
    .toContain(ourUserId)
  expect(resp['data']['onChatMessageNotification']['message']['authorUserId']).toBeNull()
  expect(resp['data']['onChatMessageNotification']['message']['author']).toBeNull()
  nextNotification = new Promise((resolve, reject) => {resolvers.push(resolve); rejectors.push(reject)})

  // other2 adds a message to the chat
  const messageId3 = uuidv4()
  variables = {chatId, messageId: messageId3, text: 'text 3'}
  resp = await other2Client.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId3)

  // verify we received the message
  resp = await nextNotification
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['onChatMessageNotification']['message']['messageId']).toBe(messageId3)
  expect(resp['data']['onChatMessageNotification']['message']['authorUserId']).toBe(other2UserId)

  // shut down our subscription
  sub.unsubscribe()
  await subInitTimeout
})


test('Message notifications from blocke[r|d] users have authorUserId but no author', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we create a group chat with both of us in it
  const chatId = uuidv4()
  let variables = {chatId, userIds: [theirUserId], messageId: uuidv4(), messageText: 'm1'}
  let resp = await ourClient.mutate({mutation: schema.createGroupChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createGroupChat']['chatId']).toBe(chatId)
  expect(resp['data']['createGroupChat']['userCount']).toBe(2)
  expect(resp['data']['createGroupChat']['users']['items'].map(u => u['userId']).sort())
    .toEqual([ourUserId, theirUserId].sort())

  // they block us
  resp = await theirClient.mutate({mutation: schema.blockUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(ourUserId)
  expect(resp['data']['blockUser']['blockedStatus']).toBe('BLOCKING')

  // they listen to message notifciations
  let next, error
  const theirNextNotification = new Promise((resolve, reject) => {next = resolve; error = reject})
  const theirSub = await theirClient
    .subscribe({query: schema.onChatMessageNotification, variables: {userId: theirUserId}})
    .subscribe({next, error})
  const theirSubInitTimeout = misc.sleep(15000)  // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541
  await misc.sleep(2000)  // let the subscription initialize

  // we add a message
  const messageId2 = uuidv4()
  variables = {chatId, messageId: messageId2, text: 'lore'}
  resp = await ourClient.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId2)

  // verify they received a notifcation for our message with no author
  resp = await theirNextNotification
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['onChatMessageNotification']['message']['messageId']).toBe(messageId2)
  expect(resp['data']['onChatMessageNotification']['message']['authorUserId']).toBe(ourUserId)
  expect(resp['data']['onChatMessageNotification']['message']['author']).toBeNull()

  // we listen to notifciations
  const ourNextNotification = new Promise((resolve, reject) => {next = resolve; error = reject})
  const ourSub = await ourClient
    .subscribe({query: schema.onChatMessageNotification, variables: {userId: ourUserId}})
    .subscribe({next, error})
  const ourSubInitTimeout = misc.sleep(15000)  // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541
  await misc.sleep(2000)  // let the subscription initialize

  // they add a message
  const messageId3 = uuidv4()
  variables = {chatId, messageId: messageId3, text: 'ipsum'}
  resp = await theirClient.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId3)

  // verify we received a notifcation for their message
  resp = await ourNextNotification
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['onChatMessageNotification']['message']['messageId']).toBe(messageId3)
  expect(resp['data']['onChatMessageNotification']['message']['authorUserId']).toBe(theirUserId)
  expect(resp['data']['onChatMessageNotification']['message']['author']).toBeNull()

  // shut down the subscriptions
  ourSub.unsubscribe()
  theirSub.unsubscribe()
  await ourSubInitTimeout
  await theirSubInitTimeout
})
