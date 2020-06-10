/* eslint-env jest */

/**
 * This test suite should be merged with tests/post-views-trending.test.js
 * before going into production.
 *
 * This is because calls to this mutation alter a global state - namely the
 * trending users/posts indexes. As such, all tests that call this mutaiton
 * have to be run sequentially, and one simple way to get that to happen
 * with jest is to put all the tests in the same test suite.
 */

const uuidv4 = require('uuid/v4')
const rp = require('request-promise-native')

const cognito = require('../utils/cognito.js')
const misc = require('../utils/misc.js')
const {mutations, queries} = require('../schema')

const imageData = misc.generateRandomJpeg(8, 8)
const imageDataB64 = new Buffer.from(imageData).toString('base64')
const jpgHeaders = {'Content-Type': 'image/jpeg'}
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Post lifecycle, visibility and trending', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a text-only post
  const postId1 = uuidv4()
  let resp = await ourClient.mutate({
    mutation: mutations.addPost,
    variables: {postId: postId1, postType: 'TEXT_ONLY', text: 'lore ipsum'},
  })
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId1)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // they add an image post that will pass verification, but don't complete it yet
  const postId2 = uuidv4()
  resp = await theirClient.mutate({mutation: mutations.addPost, variables: {postId: postId2, takenInReal: true}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId2)
  expect(resp.data.addPost.postStatus).toBe('PENDING')
  expect(resp.data.addPost.image).toBeNull()
  const uploadUrl = resp.data.addPost.imageUploadUrl

  // we check trending posts
  resp = await ourClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(1)
  expect(resp.data.trendingPosts.items[0].postId).toBe(postId1)

  // they check trending posts
  resp = await theirClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(1)
  expect(resp.data.trendingPosts.items[0].postId).toBe(postId1)

  // they upload the image, completing their post
  await rp.put({url: uploadUrl, headers: jpgHeaders, body: imageData})
  await misc.sleepUntilPostCompleted(theirClient, postId1)
  await misc.sleep(4000) // a bit more time for dynamo trending index converge

  // check that shows up in trending posts, their post should be on top
  resp = await ourClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(2)
  expect(resp.data.trendingPosts.items[0].postId).toBe(postId2)
  expect(resp.data.trendingPosts.items[1].postId).toBe(postId1)

  // check trending users still empty since the 'free trending point' doesn't apply to users
  resp = await ourClient.query({query: queries.trendingUsers})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingUsers.items).toHaveLength(0)

  // they archive their post
  resp = await theirClient.mutate({mutation: mutations.archivePost, variables: {postId: postId2}})
  expect(resp.data.archivePost.postId).toBe(postId2)
  expect(resp.data.archivePost.postStatus).toBe('ARCHIVED')

  // their post should have disappeared from trending
  resp = await theirClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(1)
  expect(resp.data.trendingPosts.items[0].postId).toBe(postId1)

  // they restore this post (trending score has been cleared)
  resp = await theirClient.mutate({mutation: mutations.restoreArchivedPost, variables: {postId: postId2}})
  expect(resp.data.restoreArchivedPost.postId).toBe(postId2)
  expect(resp.data.restoreArchivedPost.postStatus).toBe('COMPLETED')

  // we delete our post
  resp = await ourClient.mutate({mutation: mutations.deletePost, variables: {postId: postId1}})
  expect(resp.data.deletePost.postId).toBe(postId1)
  expect(resp.data.deletePost.postStatus).toBe('DELETING')

  // our post should have disappeared from trending, and theirs should not have re-appeared
  resp = await ourClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(0)

  // check trending users, should be unaffected by post archiving & deleting
  resp = await theirClient.query({query: queries.trendingUsers})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingUsers.items).toHaveLength(0)
})

test('Non-owner views contribute to trending, filter by viewedStatus, reset & delete clear trending', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await cognito.getAppSyncLogin() // user is deleted in this test case
  const [otherClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId1 = uuidv4()
  let resp = await ourClient.mutate({
    mutation: mutations.addPost,
    variables: {postId: postId1, postType: 'TEXT_ONLY', text: 'lore ipsum'},
  })
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId1)

  // they add a post
  const postId2 = uuidv4()
  resp = await theirClient.mutate({
    mutation: mutations.addPost,
    variables: {postId: postId2, postType: 'TEXT_ONLY', text: 'lore ipsum'},
  })
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId2)

  // both should show up in trending, in order with ours in the back
  resp = await otherClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(2)
  expect(resp.data.trendingPosts.items[0].postId).toBe(postId2)
  expect(resp.data.trendingPosts.items[1].postId).toBe(postId1)

  // verify we can filter trending posts based on viewed status
  resp = await ourClient.query({query: queries.trendingPosts, variables: {viewedStatus: 'VIEWED'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(1)
  expect(resp.data.trendingPosts.items[0].postId).toBe(postId1)
  resp = await ourClient.query({query: queries.trendingPosts, variables: {viewedStatus: 'NOT_VIEWED'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(1)
  expect(resp.data.trendingPosts.items[0].postId).toBe(postId2)

  // trending users should be empty
  resp = await otherClient.query({query: queries.trendingUsers})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingUsers.items).toHaveLength(0)

  // we report to have viewed our own post
  resp = await ourClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId1]}})
  expect(resp.errors).toBeUndefined()
  await misc.sleep(2000) // let dynamo converge

  // check no change in trending posts
  resp = await otherClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(2)
  expect(resp.data.trendingPosts.items[0].postId).toBe(postId2)
  expect(resp.data.trendingPosts.items[1].postId).toBe(postId1)

  // trending users should still be empty
  resp = await otherClient.query({query: queries.trendingUsers})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingUsers.items).toHaveLength(0)

  // they report to have viewed our post
  resp = await theirClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId1]}})
  expect(resp.errors).toBeUndefined()
  await misc.sleep(2000) // let dynamo converge

  // trending posts should have flipped order
  resp = await otherClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(2)
  expect(resp.data.trendingPosts.items[0].postId).toBe(postId1)
  expect(resp.data.trendingPosts.items[1].postId).toBe(postId2)

  // we should be in trending users
  resp = await otherClient.query({query: queries.trendingUsers})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingUsers.items).toHaveLength(1)
  expect(resp.data.trendingUsers.items[0].userId).toBe(ourUserId)

  // we report to have viewed our their post
  resp = await ourClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId2]}})
  expect(resp.errors).toBeUndefined()
  await misc.sleep(2000) // let dynamo converge

  // trending posts should have flipped order again
  resp = await otherClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(2)
  expect(resp.data.trendingPosts.items[0].postId).toBe(postId2)
  expect(resp.data.trendingPosts.items[1].postId).toBe(postId1)

  // we should both be in trending users
  resp = await otherClient.query({query: queries.trendingUsers})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingUsers.items).toHaveLength(2)
  expect(resp.data.trendingUsers.items[0].userId).toBe(theirUserId)
  expect(resp.data.trendingUsers.items[1].userId).toBe(ourUserId)

  // they delete themselves
  resp = await theirClient.mutate({mutation: mutations.deleteUser})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.deleteUser.userId).toBe(theirUserId)
  expect(resp.data.deleteUser.userStatus).toBe('DELETING')
  await misc.sleep(2000) // let dynamo converge

  // verify their post has disappeared from trending
  resp = await otherClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(1)
  expect(resp.data.trendingPosts.items[0].postId).toBe(postId1)

  // verify their user has disappeared from trending
  resp = await otherClient.query({query: queries.trendingUsers})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingUsers.items).toHaveLength(1)
  expect(resp.data.trendingUsers.items[0].userId).toBe(ourUserId)

  // we reset ourselves
  resp = await ourClient.mutate({mutation: mutations.resetUser})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.resetUser.userId).toBe(ourUserId)

  // verify our post has disappeared from trending
  resp = await otherClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(0)

  // verify our user has disappeared from trending
  resp = await otherClient.query({query: queries.trendingUsers})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingUsers.items).toHaveLength(0)
})

test('Blocked, private post & user visibility of posts & users in trending', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()
  const [otherClient, otherUserId] = await loginCache.getCleanLogin()

  // we add a post
  const postId1 = uuidv4()
  let resp = await ourClient.mutate({
    mutation: mutations.addPost,
    variables: {postId: postId1, postType: 'TEXT_ONLY', text: 'lore ipsum'},
  })
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId1)

  // they report to have viewed our post
  resp = await theirClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId1]}})
  expect(resp.errors).toBeUndefined()
  await misc.sleep(2000) // let dynamo converge

  // they see our post in trending
  resp = await theirClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(1)
  expect(resp.data.trendingPosts.items[0].postId).toBe(postId1)

  // they see our user in trending
  resp = await theirClient.query({query: queries.trendingUsers})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingUsers.items).toHaveLength(1)
  expect(resp.data.trendingUsers.items[0].userId).toBe(ourUserId)

  // other starts following us
  resp = await otherClient.mutate({mutation: mutations.followUser, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.followUser.followedStatus).toBe('FOLLOWING')

  // we go private
  resp = await ourClient.mutate({mutation: mutations.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.setUserDetails.userId).toBe(ourUserId)
  expect(resp.data.setUserDetails.privacyStatus).toBe('PRIVATE')
  await misc.sleep(2000) // let dynamo converge

  // verify they don't see our post in trending anymore
  resp = await theirClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(0)

  // they see still see our user in trending
  resp = await theirClient.query({query: queries.trendingUsers})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingUsers.items).toHaveLength(1)
  expect(resp.data.trendingUsers.items[0].userId).toBe(ourUserId)

  // verify other, who is following us, sees our post in trending
  resp = await otherClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(1)
  expect(resp.data.trendingPosts.items[0].postId).toBe(postId1)

  // other also sees our user in trending
  resp = await otherClient.query({query: queries.trendingUsers})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingUsers.items).toHaveLength(1)
  expect(resp.data.trendingUsers.items[0].userId).toBe(ourUserId)

  // we block other
  resp = await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: otherUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.blockUser.userId).toBe(otherUserId)
  expect(resp.data.blockUser.blockedStatus).toBe('BLOCKING')
  await misc.sleep(2000) // let dynamo converge

  // verify other no longer sees our post in trending
  resp = await otherClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(0)

  // verify other no longer sees our user in trending
  resp = await otherClient.query({query: queries.trendingUsers})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingUsers.items).toHaveLength(0)
})

test('Posts that fail verification do not end up in trending', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a image post that fails verification
  const postId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData: imageDataB64}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  expect(resp.data.addPost.isVerified).toBe(false)

  // check it does not appear in trending
  resp = await theirClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(0)

  // they report to have viewed the post
  resp = await theirClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId]}})
  expect(resp.errors).toBeUndefined()
  await misc.sleep(2000) // let dynamo converge

  // check it does not appear in trending
  resp = await theirClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(0)

  // check we do not appear in trending
  resp = await ourClient.query({query: queries.trendingUsers})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingUsers.items).toHaveLength(0)
})

test('Views of non-original posts contribute to the original post & user in trending', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()
  const [otherClient] = await loginCache.getCleanLogin()

  // they add an image post that will pass verification
  const postId1 = uuidv4()
  let resp = await theirClient.mutate({
    mutation: mutations.addPost,
    variables: {postId: postId1, takenInReal: true, imageData: imageDataB64},
  })
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId1)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  expect(resp.data.addPost.isVerified).toBe(true)
  expect(resp.data.addPost.originalPost.postId).toBe(postId1)

  // we add an image post that will have their post as the original post
  const postId2 = uuidv4()
  resp = await ourClient.mutate({
    mutation: mutations.addPost,
    variables: {postId: postId2, takenInReal: true, imageData: imageDataB64},
  })
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId2)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  expect(resp.data.addPost.isVerified).toBe(true)
  expect(resp.data.addPost.originalPost.postId).toBe(postId1)

  // we add another post that will allow us to see changes in trending
  const postId3 = uuidv4()
  resp = await ourClient.mutate({
    mutation: mutations.addPost,
    variables: {postId: postId3, postType: 'TEXT_ONLY', text: 'lore ipsum'},
  })
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId3)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // the original post and the text post should be in trending, but not the non-original one
  resp = await theirClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(2)
  expect(resp.data.trendingPosts.items[0].postId).toBe(postId3)
  expect(resp.data.trendingPosts.items[1].postId).toBe(postId1)

  // no users should be trending yet
  resp = await theirClient.query({query: queries.trendingUsers})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingUsers.items).toHaveLength(0)

  // they report to have viewed our non-original post
  resp = await theirClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId2]}})
  expect(resp.errors).toBeUndefined()
  await misc.sleep(2000) // let dynamo converge

  // trending posts should not have changed, because:
  //  - non-original post can't enter trending
  //  - they own the original post, so their view doesn't count for it
  resp = await theirClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(2)
  expect(resp.data.trendingPosts.items[0].postId).toBe(postId3)
  expect(resp.data.trendingPosts.items[1].postId).toBe(postId1)

  // no users should be trending yet
  resp = await theirClient.query({query: queries.trendingUsers})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingUsers.items).toHaveLength(0)

  // other reports to have viewed our non-original post
  resp = await otherClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId2]}})
  expect(resp.errors).toBeUndefined()
  await misc.sleep(2000) // let dynamo converge

  // other's view should have been contributed to the original post moving up in trending
  resp = await theirClient.query({query: queries.trendingPosts})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingPosts.items).toHaveLength(2)
  expect(resp.data.trendingPosts.items[0].postId).toBe(postId1)
  expect(resp.data.trendingPosts.items[1].postId).toBe(postId3)

  // they (who own the original post) should now appear as a trending user
  resp = await theirClient.query({query: queries.trendingUsers})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.trendingUsers.items).toHaveLength(1)
  expect(resp.data.trendingUsers.items[0].userId).toBe(theirUserId)
})
