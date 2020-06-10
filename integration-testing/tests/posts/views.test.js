/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const {mutations, queries} = require('../../schema')

const imageData1 = misc.generateRandomJpeg(8, 8)
const imageData2 = misc.generateRandomJpeg(8, 8)
const imageData1B64 = new Buffer.from(imageData1).toString('base64')
const imageData2B64 = new Buffer.from(imageData2).toString('base64')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Report post views', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [other1Client, other1UserId] = await loginCache.getCleanLogin()
  const [other2Client, other2UserId] = await loginCache.getCleanLogin()

  // we add two posts
  const postId1 = uuidv4()
  const postId2 = uuidv4()
  let variables = {postId: postId1, imageData: imageData1B64}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId1)
  variables = {postId: postId2, imageData: imageData2B64}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()

  // verify we have no post views
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.postViewedByCount).toBe(0)

  // verify niether of the posts have views
  resp = await ourClient.query({query: queries.post, variables: {postId: postId1}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.viewedByCount).toBe(0)
  resp = await ourClient.query({query: queries.post, variables: {postId: postId2}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.viewedByCount).toBe(0)

  // other1 reports to have viewed both posts
  resp = await other1Client.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId1, postId2]}})
  expect(resp.errors).toBeUndefined()

  // other2 reports to have viewed one post
  resp = await other2Client.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId2]}})
  expect(resp.errors).toBeUndefined()

  // we report to have viewed both posts (should not be recorded on our own posts)
  resp = await other1Client.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId1, postId2]}})
  expect(resp.errors).toBeUndefined()

  // verify our view counts are correct
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.postViewedByCount).toBe(3)

  // verify the two posts have the right viewed by counts
  resp = await ourClient.query({query: queries.post, variables: {postId: postId1}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.viewedByCount).toBe(1)
  resp = await ourClient.query({query: queries.post, variables: {postId: postId2}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.viewedByCount).toBe(2)

  // verify the two posts have the right viewedBy lists
  resp = await ourClient.query({query: queries.post, variables: {postId: postId1}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.viewedBy.items).toHaveLength(1)
  expect(resp.data.post.viewedBy.items[0].userId).toBe(other1UserId)
  resp = await ourClient.query({query: queries.post, variables: {postId: postId2}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.viewedBy.items).toHaveLength(2)
  expect(resp.data.post.viewedBy.items[0].userId).toBe(other1UserId)
  expect(resp.data.post.viewedBy.items[1].userId).toBe(other2UserId)
})

test('Cannot report post views if we are disabled', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData: imageData1B64}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // we disable ourselves
  resp = await ourClient.mutate({mutation: mutations.disableUser})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.disableUser.userId).toBe(ourUserId)
  expect(resp.data.disableUser.userStatus).toBe('DISABLED')

  // verify we cannot report post views
  await expect(
    ourClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId]}}),
  ).rejects.toThrow(/ClientError: User .* is not ACTIVE/)
})

test('Post.viewedStatus', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we a posts
  const postId = uuidv4()
  let variables = {postId, imageData: imageData1B64}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.viewedStatus).toBe('VIEWED')

  // verify they haven't viewed the post
  resp = await theirClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.viewedStatus).toBe('NOT_VIEWED')

  // they report to have viewed the post
  resp = await theirClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId]}})
  expect(resp.errors).toBeUndefined()

  // verify that's reflected in the viewedStatus
  resp = await theirClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.viewedStatus).toBe('VIEWED')
})

test('Report post views on non-completed posts are ignored', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [other1Client] = await loginCache.getCleanLogin()
  const [other2Client] = await loginCache.getCleanLogin()

  // add a pending post
  const postId1 = uuidv4()
  let variables = {postId: postId1}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId1)
  expect(resp.data.addPost.postStatus).toBe('PENDING')

  // add an archived post
  const postId2 = uuidv4()
  variables = {postId: postId2, imageData: imageData2B64}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId2)
  resp = await ourClient.mutate({mutation: mutations.archivePost, variables: {postId: postId2}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.archivePost.postId).toBe(postId2)
  expect(resp.data.archivePost.postStatus).toBe('ARCHIVED')

  // other1 reports to have viewed both posts
  resp = await other1Client.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId1, postId2]}})
  expect(resp.errors).toBeUndefined()

  // other2 reports to have viewed one post
  resp = await other2Client.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId2]}})
  expect(resp.errors).toBeUndefined()

  // we report to have viewed both posts (should not be recorded on our own posts)
  resp = await other1Client.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId1, postId2]}})
  expect(resp.errors).toBeUndefined()

  // verify the two posts have no viewed by counts
  resp = await ourClient.query({query: queries.post, variables: {postId: postId1}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.viewedByCount).toBe(0)
  resp = await ourClient.query({query: queries.post, variables: {postId: postId2}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.viewedByCount).toBe(0)
})

test('Post views are de-duplicated by user', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [other1Client] = await loginCache.getCleanLogin()
  const [other2Client] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, imageData: imageData1B64}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)

  // other1 reports to have viewed that post twice
  resp = await other1Client.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId, postId]}})
  expect(resp.errors).toBeUndefined()

  // check counts de-duplicated
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.postViewedByCount).toBe(1)

  resp = await ourClient.query({query: queries.post, variables: {postId: postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.viewedByCount).toBe(1)

  // other2 report to have viewed that post once
  resp = await other2Client.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId]}})
  expect(resp.errors).toBeUndefined()

  // check counts
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.postViewedByCount).toBe(2)

  resp = await ourClient.query({query: queries.post, variables: {postId: postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.viewedByCount).toBe(2)

  // other1 report to have viewed that post yet again
  resp = await other1Client.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId, postId]}})
  expect(resp.errors).toBeUndefined()

  // check counts have not changed
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.postViewedByCount).toBe(2)

  resp = await ourClient.query({query: queries.post, variables: {postId: postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.viewedByCount).toBe(2)
})

test('Report post views error conditions', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // must report at least one view
  let variables = {postIds: []}
  await expect(ourClient.mutate({mutation: mutations.reportPostViews, variables})).rejects.toThrow(
    /ClientError: A minimum of 1 post id /,
  )

  // can't report more than 100 views
  variables = {
    postIds: Array(101)
      .fill()
      .map(() => uuidv4()),
  }
  await expect(ourClient.mutate({mutation: mutations.reportPostViews, variables})).rejects.toThrow(
    /ClientError: A max of 100 post ids /,
  )
})

test('Post views on duplicate posts are viewed post and original post', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()
  const [otherClient, otherUserId] = await loginCache.getCleanLogin()

  // we add an image post
  const ourPostId = uuidv4()
  let variables = {postId: ourPostId, imageData: imageData1B64, takenInReal: true}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(ourPostId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  expect(resp.data.addPost.originalPost.postId).toBe(ourPostId)
  await misc.sleep(2000) // let dynamo converge

  // they add an image post that's a duplicate of ours
  const theirPostId = uuidv4()
  variables = {postId: theirPostId, imageData: imageData1B64, takenInReal: true}
  resp = await theirClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(theirPostId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  expect(resp.data.addPost.originalPost.postId).toBe(ourPostId)

  // verify the original post is our post on both posts, and there are no views on either post
  resp = await ourClient.query({query: queries.post, variables: {postId: ourPostId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(ourPostId)
  expect(resp.data.post.viewedByCount).toBe(0)
  expect(resp.data.post.originalPost.postId).toBe(ourPostId)
  resp = await theirClient.query({query: queries.post, variables: {postId: theirPostId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(theirPostId)
  expect(resp.data.post.viewedByCount).toBe(0)
  expect(resp.data.post.originalPost.postId).toBe(ourPostId)

  // other records one post view on their post
  resp = await otherClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [theirPostId]}})
  expect(resp.errors).toBeUndefined()

  // verify that showed up on their post
  resp = await theirClient.query({query: queries.post, variables: {postId: theirPostId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(theirPostId)
  expect(resp.data.post.viewedByCount).toBe(1)
  expect(resp.data.post.viewedBy.items).toHaveLength(1)
  expect(resp.data.post.viewedBy.items[0].userId).toBe(otherUserId)

  // verify that also showed up on our post
  resp = await ourClient.query({query: queries.post, variables: {postId: ourPostId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(ourPostId)
  expect(resp.data.post.viewedByCount).toBe(1)
  expect(resp.data.post.viewedBy.items).toHaveLength(1)
  expect(resp.data.post.viewedBy.items[0].userId).toBe(otherUserId)

  // verify both of our users also recored a view
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.postViewedByCount).toBe(1)
  resp = await theirClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.postViewedByCount).toBe(1)

  // they record a view on their own post
  resp = await theirClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [theirPostId]}})
  expect(resp.errors).toBeUndefined()

  // verify that did not get recorded as a view on their post
  resp = await theirClient.query({query: queries.post, variables: {postId: theirPostId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(theirPostId)
  expect(resp.data.post.viewedByCount).toBe(1)
  expect(resp.data.post.viewedBy.items).toHaveLength(1)
  expect(resp.data.post.viewedBy.items[0].userId).toBe(otherUserId)

  // verify that did not get recorded as a view on our post
  resp = await ourClient.query({query: queries.post, variables: {postId: ourPostId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(ourPostId)
  expect(resp.data.post.viewedByCount).toBe(1)
  expect(resp.data.post.viewedBy.items).toHaveLength(1)
  expect(resp.data.post.viewedBy.items[0].userId).toBe(otherUserId)

  // we record a post view on their post
  resp = await ourClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [theirPostId]}})
  expect(resp.errors).toBeUndefined()

  // verify it did get recorded on their post
  resp = await theirClient.query({query: queries.post, variables: {postId: theirPostId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(theirPostId)
  expect(resp.data.post.viewedByCount).toBe(2)
  expect(resp.data.post.viewedBy.items).toHaveLength(2)
  expect(resp.data.post.viewedBy.items[0].userId).toBe(otherUserId)
  expect(resp.data.post.viewedBy.items[1].userId).toBe(ourUserId)

  // verify that did not get recorded as a view on our post
  resp = await ourClient.query({query: queries.post, variables: {postId: ourPostId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(ourPostId)
  expect(resp.data.post.viewedByCount).toBe(1)
  expect(resp.data.post.viewedBy.items).toHaveLength(1)
  expect(resp.data.post.viewedBy.items[0].userId).toBe(otherUserId)
})
