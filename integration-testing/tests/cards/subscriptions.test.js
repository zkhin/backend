/* eslint-env jest */

const uuidv4 = require('uuid/v4')
// the aws-appsync-subscription-link pacakge expects WebSocket to be globaly defined, like in the browser
global.WebSocket = require('ws')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const {mutations, subscriptions} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Card message triggers cannot be called from external graphql client', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // verify we can't call the trigger method, even with well-formed input
  const input = {
    userId: ourUserId,
    type: 'ADDED',
    cardId: uuidv4(),
    title: 'title',
    action: 'https://real.app/go',
  }
  await expect(ourClient.mutate({mutation: mutations.triggerCardNotification, variables: {input}})).rejects.toThrow(
    /ClientError: Access denied/,
  )
})

test('Cannot subscribe to other users notifications', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we both try to subscribe to their messages
  // Note: there doesn't seem to be any error thrown at the time of subscription, it's just that
  // the subscription next() method is never triggered
  const ourNotifications = []
  const theirNotifications = []
  await ourClient.subscribe({query: subscriptions.onCardNotification, variables: {userId: theirUserId}}).subscribe({
    next: (resp) => ourNotifications.push(resp),
    error: (resp) => console.log(resp),
  })
  const theirSub = await theirClient
    .subscribe({query: subscriptions.onCardNotification, variables: {userId: theirUserId}})
    .subscribe({
      next: (resp) => theirNotifications.push(resp),
      error: (resp) => console.log(resp),
    })
  const theirSubInitTimeout = misc.sleep(15000) // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541
  await misc.sleep(2000) // let the subscription initialize

  // they create a post
  const postId = uuidv4()
  let resp = await theirClient.mutate({
    mutation: mutations.addPost,
    variables: {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'},
  })
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // we comment on their post (thus generating a card)
  const commentId = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addComment, variables: {commentId, postId, text: 'lore!'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addComment.commentId).toBe(commentId)

  // wait for some messages to show up, ensure none did for us but one did for them
  await misc.sleep(5000)
  expect(ourNotifications).toHaveLength(0)
  expect(theirNotifications).toHaveLength(1)

  // we don't unsubscribe from our subscription because
  //  - it's not actually active, although I have yet to find a way to expect() that
  //  - unsubcribing results in the AWS SDK throwing errors
  // shut down the subscription
  theirSub.unsubscribe()
  await theirSubInitTimeout
})

test('Lifecycle, format for comment activity notification', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let resp = await ourClient.mutate({
    mutation: mutations.addPost,
    variables: {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'},
  })
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // we subscribe to our cards
  const [resolvers, rejectors] = [[], []]

  const sub = await ourClient
    .subscribe({query: subscriptions.onCardNotification, variables: {userId: ourUserId}})
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

  // set up a promise that will resolve to the next message received from the subscription
  let nextNotification = new Promise((resolve, reject) => {
    resolvers.push(resolve)
    rejectors.push(reject)
  })

  // they comment on our post (thus generating a card)
  const commentId = uuidv4()
  resp = await theirClient.mutate({mutation: mutations.addComment, variables: {commentId, postId, text: 'lore!'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addComment.commentId).toBe(commentId)

  // verify the subscription received the notification and in correct format
  resp = await nextNotification
  expect(resp.errors).toBeUndefined()
  expect(resp.data.onCardNotification.userId).toBe(ourUserId)
  expect(resp.data.onCardNotification.type).toBe('ADDED')
  expect(resp.data.onCardNotification.card.cardId).toBeTruthy()
  expect(resp.data.onCardNotification.card.title).toBe('You have new comments')
  expect(resp.data.onCardNotification.card.subTitle).toBeNull()
  expect(resp.data.onCardNotification.card.action).toMatch(RegExp('^https://real.app/chat/post/'))
  expect(resp.data.onCardNotification.card.action).toContain(postId)
  const orgCard = resp.data.onCardNotification.card

  // set up a promise that will resolve to the next message received from the subscription
  nextNotification = new Promise((resolve, reject) => {
    resolvers.push(resolve)
    rejectors.push(reject)
  })

  // we report to have viewed the comment (hence deleting the card)
  resp = await ourClient.mutate({mutation: mutations.reportCommentViews, variables: {commentIds: [commentId]}})
  expect(resp.errors).toBeUndefined()

  // verify the subscription received the notification and in correct format
  resp = await nextNotification
  expect(resp.errors).toBeUndefined()
  expect(resp.data.onCardNotification.userId).toBe(ourUserId)
  expect(resp.data.onCardNotification.type).toBe('DELETED')
  expect(resp.data.onCardNotification.card).toEqual(orgCard)

  // shut down the subscription
  sub.unsubscribe()
  await subInitTimeout
})

test('Lifecycle, format for chat activity notification', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we start a chat with them
  const chatId = uuidv4()
  let resp = await ourClient.mutate({
    mutation: mutations.createDirectChat,
    variables: {userId: theirUserId, chatId, messageId: uuidv4(), messageText: 'lore ipsum'},
  })
  expect(resp.errors).toBeUndefined()
  expect(resp.data.createDirectChat.chatId).toBe(chatId)

  // we subscribe to our cards
  const [resolvers, rejectors] = [[], []]

  const sub = await ourClient
    .subscribe({query: subscriptions.onCardNotification, variables: {userId: ourUserId}})
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

  // set up a promise that will resolve to the next message received from the subscription
  let nextNotification = new Promise((resolve, reject) => {
    resolvers.push(resolve)
    rejectors.push(reject)
  })

  // they add a message to the chat (thus generating a card)
  const messageId = uuidv4()
  resp = await theirClient.mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId, text: 'lore'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addChatMessage.messageId).toBe(messageId)

  // verify the subscription received the notification and in correct format
  resp = await nextNotification
  expect(resp.errors).toBeUndefined()
  expect(resp.data.onCardNotification.userId).toBe(ourUserId)
  expect(resp.data.onCardNotification.type).toBe('ADDED')
  expect(resp.data.onCardNotification.card.cardId).toBeTruthy()
  expect(resp.data.onCardNotification.card.title).toBe('You have new messages')
  expect(resp.data.onCardNotification.card.subTitle).toBeNull()
  expect(resp.data.onCardNotification.card.action).toBe('https://real.app/chat/')
  const orgCard = resp.data.onCardNotification.card

  // set up a promise that will resolve to the next message received from the subscription
  nextNotification = new Promise((resolve, reject) => {
    resolvers.push(resolve)
    rejectors.push(reject)
  })

  // we report to have viewed the message (hence deleting the card)
  resp = await ourClient.mutate({mutation: mutations.reportChatMessageViews, variables: {messageIds: [messageId]}})
  expect(resp.errors).toBeUndefined()

  // verify the subscription received the notification and in correct format
  resp = await nextNotification
  expect(resp.errors).toBeUndefined()
  expect(resp.data.onCardNotification.userId).toBe(ourUserId)
  expect(resp.data.onCardNotification.type).toBe('DELETED')
  expect(resp.data.onCardNotification.card).toEqual(orgCard)

  // shut down the subscription
  sub.unsubscribe()
  await subInitTimeout
})
