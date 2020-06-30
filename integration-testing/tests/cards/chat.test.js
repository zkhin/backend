/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito')
const misc = require('../../utils/misc')
const {mutations, queries, subscriptions} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Unread chat message card with correct format', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

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
  let nextNotification = new Promise((resolve, reject) => {
    resolvers.push(resolve)
    rejectors.push(reject)
  })

  // we start a direct chat with them, verify no card generated for the chat we created or that first message
  const chatId = uuidv4()
  await ourClient
    .mutate({
      mutation: mutations.createDirectChat,
      variables: {userId: theirUserId, chatId, messageId: uuidv4(), messageText: 'lore ipsum'},
    })
    .then(({data}) => expect(data.createDirectChat.chatId).toBe(chatId))
  await misc.sleep(2000)
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(0)
    expect(data.self.cards.items).toHaveLength(0)
  })

  // they add a message to the chat, verify a card was generated for their chat message, has correct format
  await theirClient
    .mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: uuidv4(), text: 'lore ipsum'}})
    .then(({data}) => expect(data.addChatMessage.messageId).toBeTruthy())
  await misc.sleep(2000)
  const card1 = await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    const card = data.self.cards.items[0]
    expect(card.cardId).toBeTruthy()
    expect(card.title).toBe('You have 1 chat with new messages')
    expect(card.subTitle).toBeNull()
    expect(card.action).toBe('https://real.app/chat/')
    expect(card.thumbnail).toBeNull()
    return card
  })

  // verify subscription fired correctly with that new card
  await nextNotification.then(({data}) => {
    expect(data.onCardNotification.userId).toBe(ourUserId)
    expect(data.onCardNotification.type).toBe('ADDED')
    expect(data.onCardNotification.card).toEqual(card1)
  })
  nextNotification = new Promise((resolve, reject) => {
    resolvers.push(resolve)
    rejectors.push(reject)
  })

  // they add another message to the chat, verify card title has not changed
  await ourClient
    .mutate({
      mutation: mutations.addChatMessage,
      variables: {chatId, messageId: uuidv4(), text: 'lore ipsum'},
    })
    .then(({data}) => expect(data.addChatMessage.messageId).toBeTruthy())
  await misc.sleep(2000)
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    expect(data.self.cards.items[0].title).toBe('You have 1 chat with new messages')
  })

  // they open up a group chat with us, verify our card title changes
  const chatId2 = uuidv4()
  await ourClient
    .mutate({
      mutation: mutations.createGroupChat,
      variables: {chatId: chatId2, userIds: [ourUserId, theirUserId], messageId: uuidv4(), messageText: 'm1'},
    })
    .then(({data}) => expect(data.createGroupChat.chatId).toBe(chatId2))
  await misc.sleep(2000)
  const card2 = await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    const card = data.self.cards.items[0]
    expect(card.title).toBe('You have 2 chats with new messages')
    const {title: cardTitle, ...cardOtherFields} = card
    const {title: card1Title, ...card1OtherFields} = card1
    expect(cardTitle).not.toBe(card1Title)
    expect(cardOtherFields).toEqual(card1OtherFields)
    return card
  })

  // verify subscription fired correctly with that changed card
  await nextNotification.then(({data}) => {
    expect(data.onCardNotification.userId).toBe(ourUserId)
    expect(data.onCardNotification.type).toBe('EDITED')
    expect(data.onCardNotification.card).toEqual(card2)
  })
  nextNotification = new Promise((resolve, reject) => {
    resolvers.push(resolve)
    rejectors.push(reject)
  })

  // we report to have viewed one of the chats, verify our card title has changed back to original
  await ourClient.mutate({mutation: mutations.reportChatViews, variables: {chatIds: [chatId]}})
  await misc.sleep(2000)
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    expect(data.self.cards.items[0]).toEqual(card1)
  })

  // verify subscription fired correctly with that changed card
  await nextNotification.then(({data}) => {
    expect(data.onCardNotification.userId).toBe(ourUserId)
    expect(data.onCardNotification.type).toBe('EDITED')
    expect(data.onCardNotification.card).toEqual(card1)
  })
  nextNotification = new Promise((resolve, reject) => {
    resolvers.push(resolve)
    rejectors.push(reject)
  })

  // we report to have viewed the other chat, verify card has dissapeared
  await ourClient.mutate({mutation: mutations.reportChatViews, variables: {chatIds: [chatId2]}})
  // verify the card has disappeared
  await misc.sleep(2000)
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(0)
    expect(data.self.cards.items).toHaveLength(0)
  })

  // verify subscription fired correctly for card deletion
  await nextNotification.then(({data}) => {
    expect(data.onCardNotification.userId).toBe(ourUserId)
    expect(data.onCardNotification.type).toBe('DELETED')
    expect(data.onCardNotification.card).toEqual(card1)
  })

  // shut down the subscription
  sub.unsubscribe()
  await subInitTimeout
})
