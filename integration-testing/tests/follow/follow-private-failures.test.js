/* eslint-env jest */

const cognito = require('../../utils/cognito.js')
const schema = require('../../utils/schema.js')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Try to double-accept a follow request', async () => {
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

  // they accept the follow request
  resp = await theirClient.mutate({mutation: schema.acceptFollowerUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['acceptFollowerUser']['followerStatus']).toBe('FOLLOWING')

  // they try to accept the follow request again
  await expect(theirClient.mutate({
    mutation: schema.acceptFollowerUser,
    variables: {userId: ourUserId},
  })).rejects.toThrow()
})


test('Try to double-deny a follow request', async () => {
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

  // they accept the follow request
  resp = await theirClient.mutate({mutation: schema.denyFollowerUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['denyFollowerUser']['followerStatus']).toBe('DENIED')

  // they try to accept the follow request again
  await expect(theirClient.mutate({
    mutation: schema.denyFollowerUser,
    variables: {userId: ourUserId},
  })).rejects.toThrow()
})


test('Cant accept/deny non-existent follow requests', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [, theirUserId] = await loginCache.getCleanLogin()
  const variables = {userId: theirUserId}
  await expect(ourClient.mutate({mutation: schema.acceptFollowerUser, variables})).rejects.toThrow()
  await expect(ourClient.mutate({mutation: schema.denyFollowerUser, variables})).rejects.toThrow()
})


test('Cant request to follow a user that has blocked us', async () => {
  // us and them
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // they block us
  let resp = await theirClient.mutate({mutation: schema.blockUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we cannot request to follow them
  await expect(ourClient.mutate({
    mutation: schema.followUser,
    variables: {userId: theirUserId},
  })).rejects.toBeDefined()

  // they unblock us
  resp = await theirClient.mutate({mutation: schema.unblockUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we can request to follow them
  resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')
})


test('Cant request to follow a user that we have blocked', async () => {
  // us and them
  const [ourClient] = await loginCache.getCleanLogin()
  const [, theirUserId] = await loginCache.getCleanLogin()

  // we block them
  let resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we cannot request to follow them
  let [mutation, variables] = [schema.followUser, {userId: theirUserId}]
  await expect(ourClient.mutate({mutation, variables})).rejects.toBeDefined()

  // we unblock them
  resp = await ourClient.mutate({mutation: schema.unblockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we can request to follow them
  resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')
})
