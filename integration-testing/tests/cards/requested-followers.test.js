const {cognito, deleteDefaultCard, eventually, sleep} = require('../../utils')
const {mutations, queries, subscriptions} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Requested followers card with correct format, subscription notifications', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: other1Client} = await loginCache.getCleanLogin()
  const {client: other2Client, userId: other2UserId} = await loginCache.getCleanLogin()
  await deleteDefaultCard(ourClient)

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

  // we go private
  await ourClient
    .mutate({mutation: mutations.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
    .then(({data}) => expect(data.setUserDetails.privacyStatus).toBe('PRIVATE'))

  // verify we have no cards
  await ourClient.query({query: queries.self}).then(({data: {self: user}}) => {
    expect(user.userId).toBe(ourUserId)
    expect(user.cardCount).toBe(0)
    expect(user.cards.items).toHaveLength(0)
  })

  // other1 requests to follow us
  await other1Client
    .mutate({mutation: mutations.followUser, variables: {userId: ourUserId}})
    .then(({data}) => expect(data.followUser.followedStatus).toBe('REQUESTED'))

  // verify a card was generated for their follow request, with correct format
  const card1 = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    const card = data.self.cards.items[0]
    expect(card.cardId).toBeTruthy()
    expect(card.title).toBe('You have 1 pending follow request')
    expect(card.subTitle).toBeNull()
    expect(card.action).toBe('https://real.app/chat/')
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

  // other2 requests to follow us
  await other2Client
    .mutate({mutation: mutations.followUser, variables: {userId: ourUserId}})
    .then(({data}) => expect(data.followUser.followedStatus).toBe('REQUESTED'))

  // verify the card has changed title
  const card2 = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    const card = data.self.cards.items[0]
    expect(card.title).toBe('You have 2 pending follow requests')
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

  // other1 gives up on following us
  await other1Client
    .mutate({mutation: mutations.unfollowUser, variables: {userId: ourUserId}})
    .then(({data}) => expect(data.unfollowUser.followedStatus).toBe('NOT_FOLLOWING'))

  // verify the card now matches the original card again
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    const card = data.self.cards.items[0]
    expect(card.cardId).toBeTruthy()
    expect(card.title).toBe('You have 1 pending follow request')
    expect(card.subTitle).toBeNull()
    expect(card.action).toBe('https://real.app/chat/')
  })

  // verify subscription fired correctly with that changed card
  await nextNotification.then((notification) => {
    expect(notification.userId).toBe(ourUserId)
    expect(notification.type).toBe('EDITED')
    expect(notification.card).toEqual(card1ExcludingThumbnail)
  })
  nextNotification = new Promise((resolve) => handlers.push(resolve))

  // we accept other2's follow request
  await ourClient
    .mutate({mutation: mutations.acceptFollowerUser, variables: {userId: other2UserId}})
    .then(({data}) => expect(data.acceptFollowerUser.followerStatus).toBe('FOLLOWING'))

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
