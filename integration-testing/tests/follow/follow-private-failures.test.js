/* eslint-env jest */

const cognito = require('../../utils/cognito.js')
const { mutations } = require('../../schema')

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
  let variables = {privacyStatus: 'PRIVATE'}
  let resp = await theirClient.mutate({mutation: mutations.setUserPrivacyStatus, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['privacyStatus']).toBe('PRIVATE')

  // we request follow them
  resp = await ourClient.mutate({mutation: mutations.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('REQUESTED')

  // they accept the follow request
  resp = await theirClient.mutate({mutation: mutations.acceptFollowerUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['acceptFollowerUser']['followerStatus']).toBe('FOLLOWING')

  // they try to accept the follow request again
  await expect(theirClient.mutate({mutation: mutations.acceptFollowerUser, variables: {userId: ourUserId}}))
    .rejects.toThrow(/ClientError: .* already has status /)
})


test('Try to double-deny a follow request', async () => {
  // us and a private user
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()
  let variables = {privacyStatus: 'PRIVATE'}
  let resp = await theirClient.mutate({mutation: mutations.setUserPrivacyStatus, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['privacyStatus']).toBe('PRIVATE')

  // we request follow them
  resp = await ourClient.mutate({mutation: mutations.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('REQUESTED')

  // they accept the follow request
  resp = await theirClient.mutate({mutation: mutations.denyFollowerUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['denyFollowerUser']['followerStatus']).toBe('DENIED')

  // they try to accept the follow request again
  await expect(theirClient.mutate({mutation: mutations.denyFollowerUser, variables: {userId: ourUserId}}))
    .rejects.toThrow(/ClientError: .* already has status /)
})


test('Cant accept/deny non-existent follow requests', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [, theirUserId] = await loginCache.getCleanLogin()
  await expect(ourClient.mutate({mutation: mutations.acceptFollowerUser, variables: {userId: theirUserId}}))
    .rejects.toThrow(/ClientError: .* has not requested /)
  await expect(ourClient.mutate({mutation: mutations.denyFollowerUser, variables: {userId: theirUserId}}))
    .rejects.toThrow(/ClientError: .* has not requested /)
})


test('Cant request to follow a user that has blocked us', async () => {
  // us and them
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // they block us
  let resp = await theirClient.mutate({mutation: mutations.blockUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we cannot request to follow them
  await expect(ourClient.mutate({
    mutation: mutations.followUser,
    variables: {userId: theirUserId},
  })).rejects.toThrow('ClientError')

  // they unblock us
  resp = await theirClient.mutate({mutation: mutations.unblockUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we can request to follow them
  resp = await ourClient.mutate({mutation: mutations.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')
})


test('Cant request to follow a user that we have blocked', async () => {
  // us and them
  const [ourClient] = await loginCache.getCleanLogin()
  const [, theirUserId] = await loginCache.getCleanLogin()

  // we block them
  let resp = await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we cannot request to follow them
  let [mutation, variables] = [mutations.followUser, {userId: theirUserId}]
  await expect(ourClient.mutate({mutation, variables})).rejects.toThrow('ClientError')

  // we unblock them
  resp = await ourClient.mutate({mutation: mutations.unblockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we can request to follow them
  resp = await ourClient.mutate({mutation: mutations.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')
})
