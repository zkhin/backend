/* eslint-env jest */

const cognito = require('../../utils/cognito.js')
const schema = require('../../utils/schema.js')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Follow a private user - approved', async () => {
  // us and a private user
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()
  let resp = await theirClient.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['privacyStatus']).toBe('PRIVATE')

  // we request follow them
  resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('REQUESTED')

  // check we have moved to a REQUESTED state
  resp = await ourClient.query({query: schema.user, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['followedStatus']).toBe('REQUESTED')
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['followerStatus']).toBe('REQUESTED')

  // they accept the follow request
  resp = await theirClient.mutate({mutation: schema.acceptFollowerUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['acceptFollowerUser']['followerStatus']).toBe('FOLLOWING')

  // check we have moved to a FOLLOWING state
  resp = await ourClient.query({query: schema.user, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['followedStatus']).toBe('FOLLOWING')
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['followerStatus']).toBe('FOLLOWING')
})


test('Follow a private user - denied', async () => {
  // us and a private user
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()
  let resp = await theirClient.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['privacyStatus']).toBe('PRIVATE')

  // we request follow them
  resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('REQUESTED')

  // they deny the follow request
  resp = await theirClient.mutate({mutation: schema.denyFollowerUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['denyFollowerUser']['followerStatus']).toBe('DENIED')

  // check we have moved to a DENIED state
  resp = await ourClient.query({query: schema.user, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['followedStatus']).toBe('DENIED')
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['followerStatus']).toBe('DENIED')
})


test('Deny & then approve a preivously approved follow request', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we follow them
  let resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')

  // they decide to deny our following
  resp = await theirClient.mutate({mutation: schema.denyFollowerUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['denyFollowerUser']['followerStatus']).toBe('DENIED')

  // check we have moved to a DENIED state
  resp = await ourClient.query({query: schema.user, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['followedStatus']).toBe('DENIED')
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['followerStatus']).toBe('DENIED')

  // they decide to approve our following
  resp = await theirClient.mutate({mutation: schema.acceptFollowerUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['acceptFollowerUser']['followerStatus']).toBe('FOLLOWING')

  // check we have moved to a FOLLOWING state
  resp = await ourClient.query({query: schema.user, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['followedStatus']).toBe('FOLLOWING')
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['followerStatus']).toBe('FOLLOWING')
})


test('Cancelling follow requests', async() => {
  // us and a private user
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()
  let resp = await theirClient.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['privacyStatus']).toBe('PRIVATE')

  // we request follow them
  resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('REQUESTED')
  // we cancel that request follow them
  resp = await ourClient.mutate({mutation: schema.unfollowUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['unfollowUser']['followedStatus']).toBe('NOT_FOLLOWING')

  // we request follow them
  resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('REQUESTED')
  // they accept the follow request
  resp = await theirClient.mutate({mutation: schema.acceptFollowerUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['acceptFollowerUser']['followerStatus']).toBe('FOLLOWING')
  // we unfollow them
  resp = await ourClient.mutate({mutation: schema.unfollowUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['unfollowUser']['followedStatus']).toBe('NOT_FOLLOWING')

  // we request follow them
  resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('REQUESTED')
  // they deny the follow request
  resp = await theirClient.mutate({mutation: schema.denyFollowerUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['denyFollowerUser']['followerStatus']).toBe('DENIED')
  // we cannot unfollow them
  await expect(ourClient.mutate({mutation: schema.unfollowUser, variables: {userId: theirUserId}})).rejects.toThrow()
  // they accept the follow request
  resp = await theirClient.mutate({mutation: schema.acceptFollowerUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['acceptFollowerUser']['followerStatus']).toBe('FOLLOWING')
  // we unfollow them
  resp = await ourClient.mutate({mutation: schema.unfollowUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['unfollowUser']['followedStatus']).toBe('NOT_FOLLOWING')
})


test('Private user changing to public has follow requests taken care of', async () => {
  // new user for us, make us private
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  let resp = await ourClient.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['privacyStatus']).toBe('PRIVATE')

  // two other users
  const [other1Client, other1UserId] = await loginCache.getCleanLogin()
  const [other2Client, other2UserId] = await loginCache.getCleanLogin()

  // both request to follow us, we ignore one request and deny the other
  await other1Client.mutate({mutation: schema.followUser, variables: {userId: ourUserId}})
  await other2Client.mutate({mutation: schema.followUser, variables: {userId: ourUserId}})
  await ourClient.mutate({mutation: schema.denyFollowerUser, variables: {userId: other2UserId}})

  // verifiy we have one follow request in REQUESTED, one in DENIED, and none accepted
  resp = await ourClient.query({query: schema.ourFollowerUsers, variables: {followStatus: 'REQUESTED'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followerUsers']['items']).toHaveLength(1)
  expect(resp['data']['self']['followerUsers']['items'][0]['userId']).toBe(other1UserId)
  resp = await ourClient.query({query: schema.ourFollowerUsers, variables: {followStatus: 'DENIED'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followerUsers']['items']).toHaveLength(1)
  expect(resp['data']['self']['followerUsers']['items'][0]['userId']).toBe(other2UserId)
  resp = await ourClient.query({query: schema.ourFollowerUsers, variables: {followStatus: 'FOLLOWING'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followerUsers']['items']).toHaveLength(0)

  // now change our profile to public
  await ourClient.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PUBLIC'}})

  // verifiy we have no follow requests in REQUESTED nor DENIED, and one accepted
  resp = await ourClient.query({query: schema.ourFollowerUsers, variables: {followStatus: 'REQUESTED'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followerUsers']['items']).toHaveLength(0)
  resp = await ourClient.query({query: schema.ourFollowerUsers, variables: {followStatus: 'DENIED'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followerUsers']['items']).toHaveLength(0)
  resp = await ourClient.query({query: schema.ourFollowerUsers, variables: {followStatus: 'FOLLOWING'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followerUsers']['items']).toHaveLength(1)
  expect(resp['data']['self']['followerUsers']['items'][0]['userId']).toBe(other1UserId)
})
