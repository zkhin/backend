/* eslint-env jest */

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const { mutations, queries } = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())

/* Run me manually! I don't play well with the other tests.
 *
 * We don't want a user with username 'real' to be present in the DB while the other
 * tests run, because all new & reset'd users will auto-follow them, throwing off the
 * expected state (number of followed, number of posts in feed, etc).
 *
 * As such, running this test in parrallel with other tests can cause the other tests
 * to mitakenly fail.
 */

test.skip('new users auto-follow a user with username `real`, if they exist', async () => {
  // the real user has a random username at this point from the [before|after]_each methods
  // create a new user. Should not auto-follow anyone
  const [client, , , , username] = await loginCache.getCleanLogin()
  let resp = await client.query({query: queries.ourFollowedUsers})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.followedUsers.items).toHaveLength(0)

  // set the real user's username to 'real', give dynamo a moment to sync
  const [realClient, realUserId] = await loginCache.getCleanLogin()
  await realClient.mutate({mutation: mutations.setUsername, variables: {username: 'real'}})
  await misc.sleep(2000)

  // reset that user as a new user. Should auto-follow the real user
  await client.mutate({mutation: mutations.resetUser, variables: {newUsername: username}})
  resp = await client.query({query: queries.ourFollowedUsers})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.followedUsers.items).toHaveLength(1)
  expect(resp.data.self.followedUsers.items[0].userId).toBe(realUserId)
})
