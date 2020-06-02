/* eslint-env jest */

const cognito = require('../../utils/cognito.js')
const {mutations, queries} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Follow counts public user', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // check they have no followers or followeds
  let resp = await ourClient.query({query: queries.user, variables: {userId: theirUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.followedCount).toBe(0)
  expect(resp.data.user.followerCount).toBe(0)

  // we follow them, their follower count increments
  resp = await ourClient.mutate({mutation: mutations.followUser, variables: {userId: theirUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.followUser.followedStatus).toBe('FOLLOWING')
  expect(resp.data.followUser.followerCount).toBe(1)

  // they follow us, their followed count increments
  resp = await theirClient.mutate({mutation: mutations.followUser, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.followUser.followedStatus).toBe('FOLLOWING')
  expect(resp.data.followUser.followerCount).toBe(1)
  resp = await ourClient.query({query: queries.user, variables: {userId: theirUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.followerCount).toBe(1)
  expect(resp.data.user.followedCount).toBe(1)

  // unfollow, counts drop back down
  resp = await ourClient.mutate({mutation: mutations.unfollowUser, variables: {userId: theirUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.unfollowUser.followedStatus).toBe('NOT_FOLLOWING')
  expect(resp.data.unfollowUser.followerCount).toBe(0)
  resp = await theirClient.mutate({mutation: mutations.unfollowUser, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.unfollowUser.followedStatus).toBe('NOT_FOLLOWING')
  expect(resp.data.unfollowUser.followerCount).toBe(0)
  resp = await ourClient.query({query: queries.user, variables: {userId: theirUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.followerCount).toBe(0)
  expect(resp.data.user.followedCount).toBe(0)
})

test('Follow counts private user', async () => {
  // create two new users, both private
  const [u1Client, u1UserId] = await loginCache.getCleanLogin()
  let resp = await u1Client.mutate({mutation: mutations.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.setUserDetails.privacyStatus).toBe('PRIVATE')
  expect(resp.data.setUserDetails.followedCount).toBe(0)
  expect(resp.data.setUserDetails.followerCount).toBe(0)

  const [u2Client, u2UserId] = await loginCache.getCleanLogin()
  resp = await u2Client.mutate({mutation: mutations.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.setUserDetails.privacyStatus).toBe('PRIVATE')
  expect(resp.data.setUserDetails.followedCount).toBe(0)
  expect(resp.data.setUserDetails.followerCount).toBe(0)

  // u1 requests to follow u2, counts don't change
  resp = await u1Client.mutate({mutation: mutations.followUser, variables: {userId: u2UserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.followUser.followedStatus).toBe('REQUESTED')
  expect(resp.data.followUser.followerCount).toBe(0)
  resp = await u2Client.query({query: queries.user, variables: {userId: u2UserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.followerCount).toBe(0)
  resp = await u1Client.query({query: queries.user, variables: {userId: u1UserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.followedCount).toBe(0)

  // u2 accepts the follow request, counts go up
  resp = await u2Client.mutate({mutation: mutations.acceptFollowerUser, variables: {userId: u1UserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.acceptFollowerUser.followerStatus).toBe('FOLLOWING')
  expect(resp.data.acceptFollowerUser.followedCount).toBe(1)
  resp = await u2Client.query({query: queries.user, variables: {userId: u2UserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.followerCount).toBe(1)
  resp = await u1Client.query({query: queries.user, variables: {userId: u1UserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.followedCount).toBe(1)

  // u2 now denies the follow request, counts go down
  resp = await u2Client.mutate({mutation: mutations.denyFollowerUser, variables: {userId: u1UserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.denyFollowerUser.followerStatus).toBe('DENIED')
  expect(resp.data.denyFollowerUser.followedCount).toBe(0)
  resp = await u2Client.query({query: queries.user, variables: {userId: u2UserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.followerCount).toBe(0)
  resp = await u1Client.query({query: queries.user, variables: {userId: u1UserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.followedCount).toBe(0)

  // u2 re-accepts the follow request, counts go up
  resp = await u2Client.mutate({mutation: mutations.acceptFollowerUser, variables: {userId: u1UserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.acceptFollowerUser.followerStatus).toBe('FOLLOWING')
  expect(resp.data.acceptFollowerUser.followedCount).toBe(1)
  resp = await u2Client.query({query: queries.user, variables: {userId: u2UserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.followerCount).toBe(1)
  resp = await u1Client.query({query: queries.user, variables: {userId: u1UserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.followedCount).toBe(1)

  // unfollow, counts go back to zero
  resp = await u1Client.mutate({mutation: mutations.unfollowUser, variables: {userId: u2UserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.unfollowUser.followedStatus).toBe('NOT_FOLLOWING')
  expect(resp.data.unfollowUser.followerCount).toBe(0)
  resp = await u1Client.query({query: queries.user, variables: {userId: u2UserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.followerCount).toBe(0)
  expect(resp.data.user.followedCount).toBe(0)

  // request to follow then immediately deny, counts stay at zero
  resp = await u1Client.mutate({mutation: mutations.followUser, variables: {userId: u2UserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.followUser.followedStatus).toBe('REQUESTED')
  expect(resp.data.followUser.followerCount).toBe(0)
  resp = await u2Client.mutate({mutation: mutations.denyFollowerUser, variables: {userId: u1UserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.denyFollowerUser.followerStatus).toBe('DENIED')
  expect(resp.data.denyFollowerUser.followedCount).toBe(0)
  resp = await u1Client.query({query: queries.user, variables: {userId: u2UserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.followerCount).toBe(0)
  expect(resp.data.user.followedCount).toBe(0)
})
