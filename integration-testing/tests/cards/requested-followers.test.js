/* eslint-env jest */

const cognito = require('../../utils/cognito')
const {mutations, queries} = require('../../schema')
const misc = require('../../utils/misc')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Requested followers card with correct format', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [other1Client] = await loginCache.getCleanLogin()
  const [other2Client, other2UserId] = await loginCache.getCleanLogin()

  // we go private
  let resp = await ourClient.mutate({
    mutation: mutations.setUserPrivacyStatus,
    variables: {privacyStatus: 'PRIVATE'},
  })
  expect(resp.data.setUserDetails.privacyStatus).toBe('PRIVATE')

  // verify we have no cards
  resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(0)
  expect(resp.data.self.cards.items).toHaveLength(0)

  // other1 requests to follow us
  resp = await other1Client.mutate({mutation: mutations.followUser, variables: {userId: ourUserId}})
  expect(resp.data.followUser.followedStatus).toBe('REQUESTED')

  // verify a card was generated for their follow request
  await misc.sleep(1000) // dynamo
  resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(1)
  expect(resp.data.self.cards.items).toHaveLength(1)

  // verify that card has expected format
  let card = resp.data.self.cards.items[0]
  expect(card.cardId).toBeTruthy()
  expect(card.title).toBe('You have pending follow requests')
  expect(card.subTitle).toBeNull()
  expect(card.action).toBe('https://real.app/chat/')
  expect(card.thumbnail).toBeFalsy()

  // other2 requests to follow us
  resp = await other2Client.mutate({mutation: mutations.followUser, variables: {userId: ourUserId}})
  expect(resp.data.followUser.followedStatus).toBe('REQUESTED')

  // verify we still have just same card
  await misc.sleep(1000) // dynamo
  resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(1)
  expect(resp.data.self.cards.items).toHaveLength(1)
  expect(resp.data.self.cards.items[0].cardId).toBe(card.cardId)

  // other1 gives up on following us
  resp = await other1Client.mutate({mutation: mutations.unfollowUser, variables: {userId: ourUserId}})
  expect(resp.data.unfollowUser.followedStatus).toBe('NOT_FOLLOWING')

  // verify we still have just same card
  await misc.sleep(1000) // dynamo
  resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(1)
  expect(resp.data.self.cards.items).toHaveLength(1)
  expect(resp.data.self.cards.items[0].cardId).toBe(card.cardId)

  // we accept other2's follow request
  resp = await ourClient.mutate({mutation: mutations.acceptFollowerUser, variables: {userId: other2UserId}})
  expect(resp.data.acceptFollowerUser.followerStatus).toBe('FOLLOWING')

  // verify the card has disappeared
  await misc.sleep(1000) // dynamo
  resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(0)
  expect(resp.data.self.cards.items).toHaveLength(0)
})
