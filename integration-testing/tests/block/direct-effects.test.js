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


test('Query.getBlockedUsers, User.blockedAt respond correctly to blocking and unblocking', async () => {
  // us and them
  const [ourClient] = await loginCache.getCleanLogin()
  const [, theirUserId] = await loginCache.getCleanLogin()

  // verify we haven't blocked them
  let resp = await ourClient.query({query: schema.user, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['userId']).toBe(theirUserId)
  expect(resp['data']['user']['blockedAt']).toBeNull()

  resp = await ourClient.query({query: schema.getBlockedUsers})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getBlockedUsers']['items']).toHaveLength(0)

  // block them
  resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(theirUserId)
  expect(resp['data']['blockUser']['blockedAt']).toBeTruthy()
  const blockedAt = resp['data']['blockUser']['blockedAt']

  // verify that block shows up
  resp = await ourClient.query({query: schema.user, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['userId']).toBe(theirUserId)
  expect(resp['data']['user']['blockedAt']).toBe(blockedAt)

  resp = await ourClient.query({query: schema.getBlockedUsers})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getBlockedUsers']['items']).toHaveLength(1)
  expect(resp['data']['getBlockedUsers']['items'][0]['userId']).toBe(theirUserId)
  expect(resp['data']['getBlockedUsers']['items'][0]['blockedAt']).toBe(blockedAt)

  // unblock them
  resp = await ourClient.mutate({mutation: schema.unblockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['unblockUser']['userId']).toBe(theirUserId)
  expect(resp['data']['unblockUser']['blockedAt']).toBeNull()

  // verify that block has disappeared
  resp = await ourClient.query({query: schema.user, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['userId']).toBe(theirUserId)
  expect(resp['data']['user']['blockedAt']).toBeNull()

  resp = await ourClient.query({query: schema.getBlockedUsers})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getBlockedUsers']['items']).toHaveLength(0)
})


test('Unblocking a user we have not blocked is an error', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [, theirUserId] = await loginCache.getCleanLogin()
  let opts = {mutation: schema.unblockUser, variables: {userId: theirUserId}}
  await expect(ourClient.mutate(opts)).rejects.toBeDefined()
})


test('Double blocking a user is an error', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [, theirUserId] = await loginCache.getCleanLogin()

  // block them
  let resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(theirUserId)

  // try to block them again
  await expect(ourClient.mutate({mutation: schema.blockUser, variables: {userId: theirUserId}})).rejects.toBeDefined()
})


test('Trying to block or unblock yourself is an error', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  await expect(ourClient.mutate({mutation: schema.blockUser, variables: {userId: ourUserId}})).rejects.toBeDefined()
  await expect(ourClient.mutate({mutation: schema.unblockUser, variables: {userId: ourUserId}})).rejects.toBeDefined()
})


test('Query.getBlockedUsers ordering', async () => {
  // us and two others
  const [ourClient] = await loginCache.getCleanLogin()
  const [, other1UserId] = await loginCache.getCleanLogin()
  const [, other2UserId] = await loginCache.getCleanLogin()

  // we block both of them
  let resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: other1UserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(other1UserId)

  resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: other2UserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(other2UserId)

  // check that they appear in the right order
  resp = await ourClient.query({query: schema.getBlockedUsers})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getBlockedUsers']['items']).toHaveLength(2)
  expect(resp['data']['getBlockedUsers']['items'][0]['userId']).toBe(other2UserId)
  expect(resp['data']['getBlockedUsers']['items'][1]['userId']).toBe(other1UserId)
})


test('We can block & unblock a user that has blocked us', async () => {
  // us and them
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // they block us
  let resp = await theirClient.mutate({mutation: schema.blockUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(ourUserId)

  // verify we can still block them
  resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(theirUserId)

  // verify we can still unblock them
  resp = await ourClient.mutate({mutation: schema.unblockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['unblockUser']['userId']).toBe(theirUserId)
})
