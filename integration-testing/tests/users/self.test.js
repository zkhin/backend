/* eslint-env jest */

const cognito = require('../../utils/cognito')
const {mutations, queries} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Query.self for user that exists, matches Query.user', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  let resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  const selfItem = resp.data.self

  resp = await ourClient.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.userId).toBe(ourUserId)
  expect(resp.data.user).toEqual(selfItem)
})

test('Query.self for user that does not exist', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // reset user to remove from dynamo
  let resp = await ourClient.mutate({mutation: mutations.resetUser})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.resetUser.userId).toBe(ourUserId)

  // verify system see us as not registered yet
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors.length).toBeTruthy()
  expect(resp.errors[0].message).toEqual('User does not exist')
})

test('Query.user matches Query.self', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  let resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  const selfItem = resp.data.self

  resp = await ourClient.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.userId).toBe(ourUserId)
  expect(resp.data.user).toEqual(selfItem)
})
