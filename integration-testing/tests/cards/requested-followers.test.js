/* eslint-env jest */

const cognito = require('../../utils/cognito')
const {mutations, queries, subscriptions} = require('../../schema')
const misc = require('../../utils/misc')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Requested followers card with correct format, subscription notifications', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [other1Client] = await loginCache.getCleanLogin()
  const [other2Client, other2UserId] = await loginCache.getCleanLogin()

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

  // we go private
  await ourClient
    .mutate({mutation: mutations.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
    .then(({data}) => expect(data.setUserDetails.privacyStatus).toBe('PRIVATE'))

  // verify we have no cards
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(0)
    expect(data.self.cards.items).toHaveLength(0)
  })

  // other1 requests to follow us
  await other1Client
    .mutate({mutation: mutations.followUser, variables: {userId: ourUserId}})
    .then(({data}) => expect(data.followUser.followedStatus).toBe('REQUESTED'))

  // verify a card was generated for their follow request, with correct format
  await misc.sleep(1000) // dynamo
  const card1 = await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    const card = data.self.cards.items[0]
    expect(card.cardId).toBeTruthy()
    expect(card.title).toBe('You have 1 pending follow request')
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

  // other2 requests to follow us
  await other2Client
    .mutate({mutation: mutations.followUser, variables: {userId: ourUserId}})
    .then(({data}) => expect(data.followUser.followedStatus).toBe('REQUESTED'))

  // verify the card has changed title
  await misc.sleep(1000) // dynamo
  const card2 = await ourClient.query({query: queries.self}).then(({data}) => {
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

  // other1 gives up on following us
  await other1Client
    .mutate({mutation: mutations.unfollowUser, variables: {userId: ourUserId}})
    .then(({data}) => expect(data.unfollowUser.followedStatus).toBe('NOT_FOLLOWING'))

  // verify the card now matches the original card again
  await misc.sleep(1000) // dynamo
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

  // we accept other2's follow request
  await ourClient
    .mutate({mutation: mutations.acceptFollowerUser, variables: {userId: other2UserId}})
    .then(({data}) => expect(data.acceptFollowerUser.followerStatus).toBe('FOLLOWING'))

  // verify the card has disappeared
  await misc.sleep(1000) // dynamo
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
