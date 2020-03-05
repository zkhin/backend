/* eslint-env jest */

/**
 * This one test suite contains all calls to Mutate.reportPostViews()
 *
 * This is because calls to this mutation alter a global state - namely the
 * trending users/posts indexes. As such, all tests that call this mutaiton
 * have to be run sequentially, and one simple way to get that to happen
 * with jest is to put all the tests in the same test suite.
 */

const uuidv4 = require('uuid/v4')

const cognito = require('../utils/cognito.js')
const misc = require('../utils/misc.js')
const schema = require('../utils/schema.js')

const imageData1 = misc.generateRandomJpeg(8, 8)
const imageData2 = misc.generateRandomJpeg(8, 8)
const imageData3 = misc.generateRandomJpeg(8, 8)
const imageData1B64 = new Buffer.from(imageData1).toString('base64')
const imageData2B64 = new Buffer.from(imageData2).toString('base64')
const imageData3B64 = new Buffer.from(imageData3).toString('base64')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Report post views', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [other1Client, other1UserId] = await loginCache.getCleanLogin()
  const [other2Client, other2UserId] = await loginCache.getCleanLogin()

  // we add two posts
  const postId1 = uuidv4()
  const postId2 = uuidv4()
  let variables = {postId: postId1, mediaId: uuidv4(), imageData: imageData1B64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)
  variables = {postId: postId2, mediaId: uuidv4(), imageData: imageData2B64}
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)

  // verify we have no post views
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postViewedByCount']).toBe(0)

  // verify niether of the posts have views
  resp = await ourClient.query({query: schema.post, variables: {postId: postId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['viewedByCount']).toBe(0)
  resp = await ourClient.query({query: schema.post, variables: {postId: postId2}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['viewedByCount']).toBe(0)

  // other1 reports to have viewed both posts
  resp = await other1Client.mutate({mutation: schema.reportPostViews, variables: {postIds: [postId1, postId2]}})
  expect(resp['errors']).toBeUndefined()

  // other2 reports to have viewed one post
  resp = await other2Client.mutate({mutation: schema.reportPostViews, variables: {postIds: [postId2]}})
  expect(resp['errors']).toBeUndefined()

  // we report to have viewed both posts (should not be recorded on our own posts)
  resp = await other1Client.mutate({mutation: schema.reportPostViews, variables: {postIds: [postId1, postId2]}})
  expect(resp['errors']).toBeUndefined()

  // verify our view counts are correct
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postViewedByCount']).toBe(3)

  // verify the two posts have the right viewed by counts
  resp = await ourClient.query({query: schema.post, variables: {postId: postId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['viewedByCount']).toBe(1)
  resp = await ourClient.query({query: schema.post, variables: {postId: postId2}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['viewedByCount']).toBe(2)

  // verify the two posts have the right viewedBy lists
  resp = await ourClient.query({query: schema.postViewedBy, variables: {postId: postId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['viewedBy']['items']).toHaveLength(1)
  expect(resp['data']['post']['viewedBy']['items'][0]['userId']).toBe(other1UserId)
  resp = await ourClient.query({query: schema.postViewedBy, variables: {postId: postId2}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['viewedBy']['items']).toHaveLength(2)
  expect(resp['data']['post']['viewedBy']['items'][0]['userId']).toBe(other2UserId)
  expect(resp['data']['post']['viewedBy']['items'][1]['userId']).toBe(other1UserId)
})


test('Report post views on non-completed posts are ignored', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [other1Client] = await loginCache.getCleanLogin()
  const [other2Client] = await loginCache.getCleanLogin()

  // add a pending post
  const postId1 = uuidv4()
  let variables = {postId: postId1, mediaId: uuidv4()}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)
  expect(resp['data']['addPost']['postStatus']).toBe('PENDING')

  // add an archived post
  const postId2 = uuidv4()
  variables = {postId: postId2, mediaId: uuidv4(), imageData: imageData2B64}
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)
  resp = await ourClient.mutate({mutation: schema.archivePost, variables: {postId: postId2}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['archivePost']['postId']).toBe(postId2)
  expect(resp['data']['archivePost']['postStatus']).toBe('ARCHIVED')

  // other1 reports to have viewed both posts
  resp = await other1Client.mutate({mutation: schema.reportPostViews, variables: {postIds: [postId1, postId2]}})
  expect(resp['errors']).toBeUndefined()

  // other2 reports to have viewed one post
  resp = await other2Client.mutate({mutation: schema.reportPostViews, variables: {postIds: [postId2]}})
  expect(resp['errors']).toBeUndefined()

  // we report to have viewed both posts (should not be recorded on our own posts)
  resp = await other1Client.mutate({mutation: schema.reportPostViews, variables: {postIds: [postId1, postId2]}})
  expect(resp['errors']).toBeUndefined()

  // verify the two posts have no viewed by counts
  resp = await ourClient.query({query: schema.post, variables: {postId: postId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['viewedByCount']).toBe(0)
  resp = await ourClient.query({query: schema.post, variables: {postId: postId2}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['viewedByCount']).toBe(0)

  // verify there are no trending posts
  resp = await ourClient.query({query: schema.trendingPosts})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingPosts']['items']).toHaveLength(0)
})


test('Post views are de-duplicated by user', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [other1Client] = await loginCache.getCleanLogin()
  const [other2Client] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, mediaId: uuidv4(), imageData: imageData1B64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // other1 reports to have viewed that post twice
  resp = await other1Client.mutate({mutation: schema.reportPostViews, variables: {postIds: [postId, postId]}})
  expect(resp['errors']).toBeUndefined()

  // check counts de-duplicated
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postViewedByCount']).toBe(1)

  resp = await ourClient.query({query: schema.post, variables: {postId: postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['viewedByCount']).toBe(1)

  // other2 report to have viewed that post once
  resp = await other2Client.mutate({mutation: schema.reportPostViews, variables: {postIds: [postId]}})
  expect(resp['errors']).toBeUndefined()

  // check counts
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postViewedByCount']).toBe(2)

  resp = await ourClient.query({query: schema.post, variables: {postId: postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['viewedByCount']).toBe(2)

  // other1 report to have viewed that post yet again
  resp = await other1Client.mutate({mutation: schema.reportPostViews, variables: {postIds: [postId, postId]}})
  expect(resp['errors']).toBeUndefined()

  // check counts have not changed
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postViewedByCount']).toBe(2)

  resp = await ourClient.query({query: schema.post, variables: {postId: postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['viewedByCount']).toBe(2)
})


test('Report post views error conditions', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // must report at least one view
  let variables = {postIds: []}
  await expect(ourClient.mutate({mutation: schema.reportPostViews, variables})).rejects.toThrow('ClientError')

  // can't report more than 100 views
  variables = {postIds: Array(101).fill().map(() => uuidv4())}
  await expect(ourClient.mutate({mutation: schema.reportPostViews, variables})).rejects.toThrow('ClientError')
})


test('resetUser deletes trending items', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, mediaId: uuidv4(), imageData: imageData1B64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // they view that post
  resp = await theirClient.mutate({mutation: schema.reportPostViews, variables: {postIds: [postId]}})
  expect(resp['errors']).toBeUndefined()

  // verify we now show up in the list of trending users
  resp = await theirClient.query({query: schema.trendingUsers})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingUsers']['items']).toHaveLength(1)
  expect(resp['data']['trendingUsers']['items'][0]['userId']).toBe(ourUserId)

  // verify our post now shows up in the list of trending posts
  resp = await theirClient.query({query: schema.trendingPosts})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingPosts']['items']).toHaveLength(1)
  expect(resp['data']['trendingPosts']['items'][0]['postId']).toBe(postId)

  // we reset our user, should clear us & post from trending indexes
  await ourClient.mutate({mutation: schema.resetUser})

  // verify we now do *not* show up in the list of trending users
  resp = await theirClient.query({query: schema.trendingUsers})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingUsers']['items']).toHaveLength(0)

  // verify our post now does *not* show up in the list of trending posts
  resp = await theirClient.query({query: schema.trendingPosts})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingPosts']['items']).toHaveLength(0)
})


test('Order of trending users', async () => {
  /* Note that only the very first reporting of post views is immediately incoporated
   * into the trending users index, which limits our ability to externally test this well.
   */
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()
  const [anotherClient] = await loginCache.getCleanLogin()

  // we add one post
  const postId = uuidv4()
  let variables = {postId, mediaId: uuidv4(), imageData: imageData1B64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // they add two posts
  const postId1 = uuidv4()
  const postId2 = uuidv4()
  variables = {postId: postId1, mediaId: uuidv4(), imageData: imageData2B64}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)
  variables = {postId: postId2, mediaId: uuidv4(), imageData: imageData3B64}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)

  // verify no trending users
  resp = await ourClient.query({query: schema.trendingUsers})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingUsers']['items']).toHaveLength(0)

  // our one post gets viewed three times by the same person, while
  // their two posts each get one view
  let postIds = [postId, postId, postId, postId1, postId2]
  resp = await anotherClient.mutate({mutation: schema.reportPostViews, variables: {postIds}})
  expect(resp['errors']).toBeUndefined()

  // verify trending users has correct order
  resp = await ourClient.query({query: schema.trendingUsers})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingUsers']['items']).toHaveLength(2)
  expect(resp['data']['trendingUsers']['items'][0]['userId']).toBe(theirUserId)
  expect(resp['data']['trendingUsers']['items'][1]['userId']).toBe(ourUserId)
})


test('We do not see trending users that have blocked us, but see all others', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [other1Client] = await loginCache.getCleanLogin()
  const [other2Client] = await loginCache.getCleanLogin()

  // other1 blocks us
  let resp = await other1Client.mutate({mutation: schema.blockUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()

  // other1 adds a post
  const postId1 = uuidv4()
  let variables = {postId: postId1, mediaId: uuidv4(), imageData: imageData1B64}
  resp = await other1Client.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)

  // we add a post
  const postId2 = uuidv4()
  variables = {postId: postId2, mediaId: uuidv4(), imageData: imageData2B64}
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)

  // verify no trending users
  resp = await ourClient.query({query: schema.trendingUsers})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingUsers']['items']).toHaveLength(0)

  // all posts get viewed
  resp = await other2Client.mutate({mutation: schema.reportPostViews, variables: {postIds: [postId1, postId2]}})
  expect(resp['errors']).toBeUndefined()

  // verify trending users looks correct, including the items that are batch filled in
  resp = await ourClient.query({query: schema.trendingUsers})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingUsers']['items']).toHaveLength(1)
  expect(resp['data']['trendingUsers']['items'][0]['userId']).toBe(ourUserId)
  expect(resp['data']['trendingUsers']['items'][0]['blockerStatus']).toBe('SELF')
})


test('We see our own trending posts correctly', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add two posts
  const postId1 = uuidv4()
  const postId2 = uuidv4()
  let variables = {postId: postId1, mediaId: uuidv4(), imageData: imageData1B64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)
  variables = {postId: postId2, mediaId: uuidv4(), imageData: imageData2B64}
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)

  // verify no trending posts
  resp = await ourClient.query({query: schema.trendingPosts})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingPosts']['items']).toHaveLength(0)

  // both posts get viewed
  resp = await theirClient.mutate({mutation: schema.reportPostViews, variables: {postIds: [postId1, postId2]}})
  expect(resp['errors']).toBeUndefined()

  // verify trending posts looks correct, including the items that are batch filled in
  resp = await ourClient.query({query: schema.trendingPosts})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingPosts']['items']).toHaveLength(2)

  // Note: no way to guarantee order in the trending post index,
  // because only the first view is immediately incorporated into the score.
  const firstPost = resp['data']['trendingPosts']['items'][0]
  const secondPost = resp['data']['trendingPosts']['items'][1]
  const post1 = firstPost['postId'] == postId1 ? firstPost : secondPost
  const post2 = secondPost['postId'] == postId2 ? secondPost : firstPost

  expect(post1['postId']).toBe(postId1)
  expect(post1['postedBy']['userId']).toBe(ourUserId)
  expect(post1['postedBy']['blockerStatus']).toBe('SELF')
  expect(post1['postedBy']['privacyStatus']).toBe('PUBLIC')
  expect(post1['postedBy']['followedStatus']).toBe('SELF')

  expect(post2['postId']).toBe(postId2)
  expect(post2['postedBy']['userId']).toBe(ourUserId)
  expect(post2['postedBy']['blockerStatus']).toBe('SELF')
  expect(post2['postedBy']['privacyStatus']).toBe('PUBLIC')
  expect(post2['postedBy']['followedStatus']).toBe('SELF')
})


test('We see public users trending posts correctly', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [other1Client, other1UserId] = await loginCache.getCleanLogin()
  const [other2Client, other2UserId] = await loginCache.getCleanLogin()

  // we follow other 1
  let resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: other1UserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')

  // other 1 adds a post
  const postId1 = uuidv4()
  let variables = {postId: postId1, mediaId: uuidv4(), imageData: imageData1B64}
  resp = await other1Client.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)

  // other 2 adds a post
  const postId2 = uuidv4()
  variables = {postId: postId2, mediaId: uuidv4(), imageData: imageData2B64}
  resp = await other2Client.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)

  // verify no trending posts
  resp = await ourClient.query({query: schema.trendingPosts})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingPosts']['items']).toHaveLength(0)

  // both posted get viewed
  resp = await ourClient.mutate({mutation: schema.reportPostViews, variables: {postIds: [postId1, postId2]}})
  expect(resp['errors']).toBeUndefined()

  // verify trending posts looks correct, including the items that are batch filled in
  resp = await ourClient.query({query: schema.trendingPosts})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingPosts']['items']).toHaveLength(2)

  // Note: no way to guarantee order in the trending post index,
  // because only the first view is immediately incorporated into the score.
  const firstPost = resp['data']['trendingPosts']['items'][0]
  const secondPost = resp['data']['trendingPosts']['items'][1]
  const post1 = firstPost['postId'] == postId1 ? firstPost : secondPost
  const post2 = secondPost['postId'] == postId2 ? secondPost : firstPost

  expect(post1['postId']).toBe(postId1)
  expect(post1['postedBy']['userId']).toBe(other1UserId)
  expect(post1['postedBy']['blockerStatus']).toBe('NOT_BLOCKING')
  expect(post1['postedBy']['privacyStatus']).toBe('PUBLIC')
  expect(post1['postedBy']['followedStatus']).toBe('FOLLOWING')

  expect(post2['postId']).toBe(postId2)
  expect(post2['postedBy']['userId']).toBe(other2UserId)
  expect(post2['postedBy']['blockerStatus']).toBe('NOT_BLOCKING')
  expect(post2['postedBy']['privacyStatus']).toBe('PUBLIC')
  expect(post2['postedBy']['followedStatus']).toBe('NOT_FOLLOWING')
})


test('We see posts of private users only if we are following them', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [other1Client, other1UserId] = await loginCache.getCleanLogin()
  const [other2Client] = await loginCache.getCleanLogin()

  // we follow other 1
  let resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: other1UserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')

  // other 1 goes private
  resp = await other1Client.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['privacyStatus']).toBe('PRIVATE')

  // other 2 goes private
  resp = await other2Client.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['privacyStatus']).toBe('PRIVATE')

  // other 1 adds a post
  const postId1 = uuidv4()
  let variables = {postId: postId1, mediaId: uuidv4(), imageData: imageData1B64}
  resp = await other1Client.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)

  // other 2 adds a post
  const postId2 = uuidv4()
  variables = {postId: postId2, mediaId: uuidv4(), imageData: imageData2B64}
  resp = await other2Client.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)

  // verify no trending posts
  resp = await ourClient.query({query: schema.trendingPosts})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingPosts']['items']).toHaveLength(0)

  // both posts viewed
  resp = await ourClient.mutate({mutation: schema.reportPostViews, variables: {postIds: [postId1, postId2]}})
  expect(resp['errors']).toBeUndefined()

  // verify trending posts looks correct, including the items that are batch filled in
  resp = await ourClient.query({query: schema.trendingPosts})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingPosts']['items']).toHaveLength(1)

  const firstPost = resp['data']['trendingPosts']['items'][0]
  expect(firstPost['postId']).toBe(postId1)
  expect(firstPost['postedBy']['userId']).toBe(other1UserId)
  expect(firstPost['postedBy']['blockerStatus']).toBe('NOT_BLOCKING')
  expect(firstPost['postedBy']['privacyStatus']).toBe('PRIVATE')
  expect(firstPost['postedBy']['followedStatus']).toBe('FOLLOWING')
})


test('We do not see trending posts of users that have blocked us', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // they block us
  let resp = await theirClient.mutate({mutation: schema.blockUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()

  // they add a post
  const postId1 = uuidv4()
  let variables = {postId: postId1, mediaId: uuidv4(), imageData: imageData1B64}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)

  // we add a post
  const postId2 = uuidv4()
  variables = {postId: postId2, mediaId: uuidv4(), imageData: imageData2B64}
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)

  // verify no trending posts
  resp = await ourClient.query({query: schema.trendingPosts})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingPosts']['items']).toHaveLength(0)

  // they view both posts
  resp = await theirClient.mutate({mutation: schema.reportPostViews, variables: {postIds: [postId1, postId2]}})
  expect(resp['errors']).toBeUndefined()

  // verify trending posts looks correct, including the items that are batch filled in
  resp = await ourClient.query({query: schema.trendingPosts})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingPosts']['items']).toHaveLength(1)

  const firstPost = resp['data']['trendingPosts']['items'][0]
  expect(firstPost['postId']).toBe(postId2)
  expect(firstPost['postedBy']['userId']).toBe(ourUserId)
  expect(firstPost['postedBy']['blockerStatus']).toBe('SELF')
  expect(firstPost['postedBy']['privacyStatus']).toBe('PUBLIC')
  expect(firstPost['postedBy']['followedStatus']).toBe('SELF')
})


test('Post views on duplicate posts are viewed post and original post, only original get trending', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()
  const [otherClient, otherUserId] = await loginCache.getCleanLogin()

  // we add a media post
  const ourPostId = uuidv4()
  let variables = {postId: ourPostId, mediaId: uuidv4(), imageData: imageData1B64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(ourPostId)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['addPost']['originalPost']['postId']).toBe(ourPostId)
  await misc.sleep(2000)  // let dynamo converge

  // they add a media post that's a duplicate of ours
  const theirPostId = uuidv4()
  variables = {postId: theirPostId, mediaId: uuidv4(), imageData: imageData1B64}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(theirPostId)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['addPost']['originalPost']['postId']).toBe(ourPostId)

  // verify the original post is our post on both posts, and there are no views on either post
  resp = await ourClient.query({query: schema.post, variables: {postId: ourPostId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(ourPostId)
  expect(resp['data']['post']['viewedByCount']).toBe(0)
  expect(resp['data']['post']['originalPost']['postId']).toBe(ourPostId)
  resp = await theirClient.query({query: schema.post, variables: {postId: theirPostId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(theirPostId)
  expect(resp['data']['post']['viewedByCount']).toBe(0)
  expect(resp['data']['post']['originalPost']['postId']).toBe(ourPostId)

  // other records one post view on their post
  resp = await otherClient.mutate({mutation: schema.reportPostViews, variables: {postIds: [theirPostId]}})
  expect(resp['errors']).toBeUndefined()

  // verify that showed up on their post
  resp = await theirClient.query({query: schema.post, variables: {postId: theirPostId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(theirPostId)
  expect(resp['data']['post']['viewedByCount']).toBe(1)
  expect(resp['data']['post']['viewedBy']['items']).toHaveLength(1)
  expect(resp['data']['post']['viewedBy']['items'][0]['userId']).toBe(otherUserId)

  // verify that also showed up on our post
  resp = await ourClient.query({query: schema.post, variables: {postId: ourPostId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(ourPostId)
  expect(resp['data']['post']['viewedByCount']).toBe(1)
  expect(resp['data']['post']['viewedBy']['items']).toHaveLength(1)
  expect(resp['data']['post']['viewedBy']['items'][0]['userId']).toBe(otherUserId)

  // verify both of our users also recored a view
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postViewedByCount']).toBe(1)
  resp = await theirClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postViewedByCount']).toBe(1)

  // check trending posts - only our post should show up there
  resp = await theirClient.query({query: schema.trendingPosts})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingPosts']['items']).toHaveLength(1)
  expect(resp['data']['trendingPosts']['items'][0]['postId']).toBe(ourPostId)

  // check trending users - only we should show up there
  resp = await theirClient.query({query: schema.trendingUsers})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingUsers']['items']).toHaveLength(1)
  expect(resp['data']['trendingUsers']['items'][0]['userId']).toBe(ourUserId)

  // they record a view on their own post
  resp = await theirClient.mutate({mutation: schema.reportPostViews, variables: {postIds: [theirPostId]}})
  expect(resp['errors']).toBeUndefined()

  // verify that did not get recorded as a view on their post
  resp = await theirClient.query({query: schema.post, variables: {postId: theirPostId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(theirPostId)
  expect(resp['data']['post']['viewedByCount']).toBe(1)
  expect(resp['data']['post']['viewedBy']['items']).toHaveLength(1)
  expect(resp['data']['post']['viewedBy']['items'][0]['userId']).toBe(otherUserId)

  // verify that did not get recorded as a view on our post
  resp = await ourClient.query({query: schema.post, variables: {postId: ourPostId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(ourPostId)
  expect(resp['data']['post']['viewedByCount']).toBe(1)
  expect(resp['data']['post']['viewedBy']['items']).toHaveLength(1)
  expect(resp['data']['post']['viewedBy']['items'][0]['userId']).toBe(otherUserId)

  // we record a post view on their post
  resp = await ourClient.mutate({mutation: schema.reportPostViews, variables: {postIds: [theirPostId]}})
  expect(resp['errors']).toBeUndefined()

  // verify it did get recorded on their post
  resp = await theirClient.query({query: schema.post, variables: {postId: theirPostId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(theirPostId)
  expect(resp['data']['post']['viewedByCount']).toBe(2)
  expect(resp['data']['post']['viewedBy']['items']).toHaveLength(2)
  expect(resp['data']['post']['viewedBy']['items'][0]['userId']).toBe(ourUserId)
  expect(resp['data']['post']['viewedBy']['items'][1]['userId']).toBe(otherUserId)

  // verify that did not get recorded as a view on our post
  resp = await ourClient.query({query: schema.post, variables: {postId: ourPostId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(ourPostId)
  expect(resp['data']['post']['viewedByCount']).toBe(1)
  expect(resp['data']['post']['viewedBy']['items']).toHaveLength(1)
  expect(resp['data']['post']['viewedBy']['items'][0]['userId']).toBe(otherUserId)
})


test('Archived posts do not show up as trending', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // add a post
  const postId = uuidv4()
  let variables = {postId, mediaId: uuidv4(), imageData: imageData1B64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // view the post
  resp = await theirClient.mutate({mutation: schema.reportPostViews, variables: {postIds: [postId]}})
  expect(resp['errors']).toBeUndefined()

  // verify it shows up as trending
  resp = await ourClient.query({query: schema.trendingPosts})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingPosts']['items']).toHaveLength(1)
  expect(resp['data']['trendingPosts']['items'][0]['postId']).toBe(postId)

  // archive the post
  resp = await ourClient.mutate({mutation: schema.archivePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['archivePost']['postStatus']).toBe('ARCHIVED')

  // verify the post no longer shows up as trending
  resp = await ourClient.query({query: schema.trendingPosts})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['trendingPosts']['items']).toHaveLength(0)
})
