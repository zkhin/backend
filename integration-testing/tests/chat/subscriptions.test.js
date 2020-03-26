/* eslint-env jest */

const moment = require('moment')
const uuidv4 = require('uuid/v4')
// the aws-appsync-subscription-link pacakge expects WebSocket to be globaly defined, like in the browser
global.WebSocket = require('ws')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const schema = require('../../utils/schema.js')

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


test('Cannot subscribe chats that we are not part of', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [other1Client] = await loginCache.getCleanLogin()
  const [other2Client, other2UserId] = await loginCache.getCleanLogin()

  // other1 opens a chat with other2
  const [chatId, messageId1, text1] = [uuidv4(), uuidv4(), 'hey this is msg 1']
  let variables = {userId: other2UserId, chatId, messageId: messageId1, messageText: text1}
  let resp = await other1Client.mutate({mutation: schema.createDirectChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createDirectChat']['chatId']).toBe(chatId)
  expect(resp['data']['createDirectChat']['messages']['items']).toHaveLength(1)
  expect(resp['data']['createDirectChat']['messages']['items'][0]['messageId']).toBe(messageId1)

  // verify we cannot subscribe to their chat
  // Note: there doesn't seem to be any error thrown at the time of subscription, it's just that
  // the subscription next() method is never triggered
  const msgNotifications = []
  await ourClient
    .subscribe({query: schema.onChatMessageNotification, variables: {chatId}})
    .subscribe({next: resp => { msgNotifications.push(resp) }})

  const [messageId2, text2] = [uuidv4(), 'lore ipsum']
  variables = {chatId, messageId: messageId2, text: text2}
  resp = await other2Client.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId2)
  expect(resp['data']['addChatMessage']['chat']['chatId']).toBe(chatId)

  // wait for some messages to show up, ensure none did
  await misc.sleep(5000)
  expect(msgNotifications).toEqual([])

  // we don't unsubscribe from the subscription because
  //  - it's not actually active, although I have yet to find a way to expect() that
  //  - unsubcribing results in the AWS SDK throwing errors
})


test('Multiple messages notifications fire', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we open a chat with them
  const [chatId, messageId1, text1] = [uuidv4(), uuidv4(), 'msg 1']
  let variables = {userId: theirUserId, chatId, messageId: messageId1, messageText: text1}
  let resp = await ourClient.mutate({mutation: schema.createDirectChat, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createDirectChat']['chatId']).toBe(chatId)
  expect(resp['data']['createDirectChat']['messages']['items']).toHaveLength(1)
  expect(resp['data']['createDirectChat']['messages']['items'][0]['messageId']).toBe(messageId1)

  // we subscribe to the chat for messages
  const ourMsgNotifications = []
  const ourSub = await ourClient
    .subscribe({query: schema.onChatMessageNotification, variables: {chatId}})
    .subscribe({next: resp => { ourMsgNotifications.push(resp) }})
  const ourSubInitTimeout = misc.sleep(15000)  // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541

  // they subscribe to the chat for messages
  const theirMsgNotifications = []
  const theirSub = await theirClient
    .subscribe({query: schema.onChatMessageNotification, variables: {chatId}})
    .subscribe({next: resp => { theirMsgNotifications.push(resp) }})
  const theirSubInitTimeout = misc.sleep(15000)  // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541
  await misc.sleep(2000)  // let the subscription initialize

  // they post a message to the chat
  const [messageId2, text2] = [uuidv4(), 'msg 2']
  variables = {chatId, messageId: messageId2, text: text2}
  resp = await theirClient.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId2)
  expect(resp['data']['addChatMessage']['chat']['chatId']).toBe(chatId)

  // we post a message to the chat
  const [messageId3, text3] = [uuidv4(), 'msg 2']
  variables = {chatId, messageId: messageId3, text: text3}
  resp = await theirClient.mutate({mutation: schema.addChatMessage, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addChatMessage']['messageId']).toBe(messageId3)
  expect(resp['data']['addChatMessage']['chat']['chatId']).toBe(chatId)

  // wait give the message a sec to show up
  await misc.sleep(2000)
  expect(ourMsgNotifications).toHaveLength(2)
  expect(ourMsgNotifications[0]['data']['onChatMessageNotification']['messageId']).toBe(messageId2)
  expect(ourMsgNotifications[1]['data']['onChatMessageNotification']['messageId']).toBe(messageId3)
  expect(theirMsgNotifications).toEqual(ourMsgNotifications)

  ourSub.unsubscribe()
  theirSub.unsubscribe()
  await ourSubInitTimeout
  await theirSubInitTimeout
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
    .subscribe({query: schema.onChatMessageNotification, variables: {chatId}})
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
  expect(resp['data']['onChatMessageNotification']).toEqual({
    'messageId': messageId2,
    'chatId': chatId,
    'authorUserId': theirUserId,
    'type': 'ADDED',
    'text': text2,
    'textTaggedUserIds': [
      {'tag': `@${ourUsername}`, 'userId': ourUserId, '__typename': 'TextTaggedUserId'},
    ],
    'createdAt': createdAt,
    'lastEditedAt': null,
    '__typename': 'ChatMessageNotification',
  })

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
  expect(resp['data']['onChatMessageNotification']).toEqual({
    'messageId': messageId2,
    'chatId': chatId,
    'authorUserId': theirUserId,
    'type': 'EDITED',
    'text': text3,
    'textTaggedUserIds': [
      {'tag': `@${theirUsername}`, 'userId': theirUserId, '__typename': 'TextTaggedUserId'},
    ],
    'createdAt': createdAt,
    'lastEditedAt': lastEditedAt,
    '__typename': 'ChatMessageNotification',
  })

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
  expect(resp['data']['onChatMessageNotification']).toEqual({
    'messageId': messageId2,
    'chatId': chatId,
    'authorUserId': theirUserId,
    'type': 'DELETED',
    'text': text3,
    'textTaggedUserIds': [
      {'tag': `@${theirUsername}`, 'userId': theirUserId, '__typename': 'TextTaggedUserId'},
    ],
    'createdAt': createdAt,
    'lastEditedAt': lastEditedAt,
    '__typename': 'ChatMessageNotification',
  })

  sub.unsubscribe()
  await subInitTimeout
})
