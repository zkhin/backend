/**
 * This test suite cannot run in parrallel with others because it
 * depends on global state - namely the 'real' user.
 */

const cognito = require('../../utils/cognito')
const misc = require('../../utils/misc')
const {mutations, queries} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()
jest.retryTimes(1)

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('new users auto-follow a user with username `real`, if they exist', async () => {
  // the real user has a random username at this point from the [before|after]_each methods
  // create a new user. Should not auto-follow anyone
  const {client, username} = await loginCache.getCleanLogin()
  let resp = await client.query({query: queries.ourFollowedUsers})
  expect(resp.data.self.followedUsers.items).toHaveLength(0)

  // set the real user's username to 'real', give dynamo a moment to sync
  const {client: realClient, userId: realUserId} = await loginCache.getCleanLogin()
  await realClient.mutate({mutation: mutations.setUsername, variables: {username: 'real'}})
  await misc.sleep(2000)

  // reset that user as a new user. Should auto-follow the real user
  await client.mutate({mutation: mutations.resetUser, variables: {newUsername: username}})
  resp = await client.query({query: queries.ourFollowedUsers})
  expect(resp.data.self.followedUsers.items).toHaveLength(1)
  expect(resp.data.self.followedUsers.items[0].userId).toBe(realUserId)
})
