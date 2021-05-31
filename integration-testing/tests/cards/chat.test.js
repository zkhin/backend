const {v4: uuidv4} = require('uuid')

const {cognito, deleteDefaultCard, eventually, sleep} = require('../../utils')
const {mutations, queries, subscriptions} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Unread chat message card with correct format', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()
  await Promise.all([ourClient, theirClient].map(deleteDefaultCard))

  // we subscribe to our cards
  const handlers = []
  const sub = await ourClient
    .subscribe({query: subscriptions.onCardNotification, variables: {userId: ourUserId}})
    .subscribe({
      next: ({data: {onCardNotification: notification}}) => {
        const handler = handlers.shift()
        expect(handler).toBeDefined()
        handler(notification)
      },
      error: (response) => expect({cause: 'Subscription error()', response}).toBeUndefined(),
    })
  const subInitTimeout = sleep('subTimeout')
  await sleep('subInit')
  let nextNotification = new Promise((resolve) => handlers.push(resolve))

  // we start a direct chat with them, verify no card generated for the chat we created or that first message
  const chatId = uuidv4()
  await ourClient
    .mutate({
      mutation: mutations.createDirectChat,
      variables: {userId: theirUserId, chatId, messageId: uuidv4(), messageText: 'lore ipsum'},
    })
    .then(({data}) => expect(data.createDirectChat.chatId).toBe(chatId))
  await sleep()
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(0)
    expect(data.self.cards.items).toHaveLength(0)
  })

  // they add a message to the chat, verify a card is generated for their chat message, has correct format
  await theirClient
    .mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: uuidv4(), text: 'lore ipsum'}})
    .then(({data}) => expect(data.addChatMessage.messageId).toBeTruthy())
  const card1 = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
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
  const {thumbnail: card1Thumbnail, ...card1ExcludingThumbnail} = card1
  expect(card1Thumbnail).toBeNull()

  // verify subscription fired correctly with that new card
  await nextNotification.then((notification) => {
    expect(notification.userId).toBe(ourUserId)
    expect(notification.type).toBe('ADDED')
    expect(notification.card).toEqual(card1ExcludingThumbnail)
  })
  nextNotification = new Promise((resolve) => handlers.push(resolve))

  // they add another message to the chat, verify card title does not change
  await ourClient
    .mutate({
      mutation: mutations.addChatMessage,
      variables: {chatId, messageId: uuidv4(), text: 'lore ipsum'},
    })
    .then(({data}) => expect(data.addChatMessage.messageId).toBeTruthy())
  await sleep()
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
  const card2 = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
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
  const {thumbnail: card2Thumbnail, ...card2ExcludingThumbnail} = card2
  expect(card2Thumbnail).toBeNull()

  // verify subscription fired correctly with that changed card
  await nextNotification.then((notification) => {
    expect(notification.userId).toBe(ourUserId)
    expect(notification.type).toBe('EDITED')
    expect(notification.card).toEqual(card2ExcludingThumbnail)
  })
  nextNotification = new Promise((resolve) => handlers.push(resolve))

  // we report to have viewed one of the chats, verify our card title has changed back to original
  await ourClient.mutate({mutation: mutations.reportChatViews, variables: {chatIds: [chatId]}})
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    expect(data.self.cards.items[0]).toEqual(card1)
  })

  // verify subscription fired correctly with that changed card
  await nextNotification.then((notification) => {
    expect(notification.userId).toBe(ourUserId)
    expect(notification.type).toBe('EDITED')
    expect(notification.card).toEqual(card1ExcludingThumbnail)
  })
  nextNotification = new Promise((resolve) => handlers.push(resolve))

  // we report to have viewed the other chat, verify card has dissapeared
  await ourClient.mutate({mutation: mutations.reportChatViews, variables: {chatIds: [chatId2]}})
  // verify the card has disappeared
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(0)
    expect(data.self.cards.items).toHaveLength(0)
  })

  // verify subscription fired correctly for card deletion
  await nextNotification.then((notification) => {
    expect(notification.userId).toBe(ourUserId)
    expect(notification.type).toBe('DELETED')
    expect(notification.card).toEqual(card1ExcludingThumbnail)
  })

  // shut down the subscription
  sub.unsubscribe()
  await subInitTimeout
})
