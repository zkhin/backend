/* eslint-env jest */

const fs = require('fs')
const path = require('path')
const rp = require('request-promise-native')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const {mutations, queries} = require('../../schema')

const imageBytes = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg'))
const imageData = new Buffer.from(imageBytes).toString('base64')
const imageHeaders = {'Content-Type': 'image/jpeg'}

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Archiving an image post', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // we upload an image post
  const postId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.image).toBeTruthy()

  // check we see that post in the feed and in the posts
  resp = await ourClient.query({query: queries.selfFeed})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.feed.items).toHaveLength(1)
  expect(resp.data.self.feed.items[0].postId).toBe(postId)
  expect(resp.data.self.feed.items[0].image.url).toBeTruthy()
  expect(resp.data.self.feed.items[0].imageUploadUrl).toBeNull()

  resp = await ourClient.query({query: queries.userPosts, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.posts.items).toHaveLength(1)
  expect(resp.data.user.posts.items[0].postId).toBe(postId)

  // archive the post
  resp = await ourClient.mutate({mutation: mutations.archivePost, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.archivePost.postStatus).toBe('ARCHIVED')

  // post should be gone from the normal queries - feed, posts
  resp = await ourClient.query({query: queries.selfFeed})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.feed.items).toHaveLength(0)

  resp = await ourClient.query({query: queries.userPosts, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.posts.items).toHaveLength(0)

  // post should be visible when specifically requesting archived posts
  resp = await ourClient.query({query: queries.userPosts, variables: {userId: ourUserId, postStatus: 'ARCHIVED'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.posts.items).toHaveLength(1)
  expect(resp.data.user.posts.items[0].postId).toBe(postId)
})

test('Cant archive a post in PENDING status', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we create a post, leave it with pending status
  const postId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('PENDING')

  // verify we can't archive that post
  await expect(ourClient.mutate({mutation: mutations.archivePost, variables: {postId}})).rejects.toThrow(
    /ClientError: Cannot archive post with status /,
  )
})

test('Cant archive a post or restore an archived post if we are disabled', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // we create a post
  const postId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // we archive that post
  resp = await ourClient.mutate({mutation: mutations.archivePost, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.archivePost.postId).toBe(postId)
  expect(resp.data.archivePost.postStatus).toBe('ARCHIVED')

  // we create a second post
  const postId2 = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId: postId2, imageData}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId2)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // we disable ourselves
  resp = await ourClient.mutate({mutation: mutations.disableUser})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.disableUser.userId).toBe(ourUserId)
  expect(resp.data.disableUser.userStatus).toBe('DISABLED')

  // verify we can't archive the second post
  await expect(ourClient.mutate({mutation: mutations.archivePost, variables: {postId: postId2}})).rejects.toThrow(
    /ClientError: User .* is not ACTIVE/,
  )

  // verify we can't restore the first post
  await expect(ourClient.mutate({mutation: mutations.restoreArchivedPost, variables: {postId}})).rejects.toThrow(
    /ClientError: User .* is not ACTIVE/,
  )
})

test('Archiving an image post does not affect image urls', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we uplaod an image post
  const postId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  const image = resp.data.addPost.image
  expect(image.url).toBeTruthy()

  // archive the post
  resp = await ourClient.mutate({mutation: mutations.archivePost, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.archivePost.postStatus).toBe('ARCHIVED')
  expect(resp.data.archivePost.imageUploadUrl).toBeNull()
  expect(resp.data.archivePost.image.url).toBeTruthy()

  // check the url bases have not changed
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.postStatus).toBe('ARCHIVED')
  const newImage = resp.data.post.image
  expect(image.url.split('?')[0]).toBe(newImage.url.split('?')[0])
  expect(image.url4k.split('?')[0]).toBe(newImage.url4k.split('?')[0])
  expect(image.url1080p.split('?')[0]).toBe(newImage.url1080p.split('?')[0])
  expect(image.url480p.split('?')[0]).toBe(newImage.url480p.split('?')[0])
  expect(image.url64p.split('?')[0]).toBe(newImage.url64p.split('?')[0])
})

test('Restoring an archived image post', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // we upload an image post
  const postId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.image).toBeTruthy()

  // archive the post
  resp = await ourClient.mutate({mutation: mutations.archivePost, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.archivePost.postStatus).toBe('ARCHIVED')
  expect(resp.data.archivePost.image).toBeTruthy()

  // restore the post
  resp = await ourClient.mutate({mutation: mutations.restoreArchivedPost, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.restoreArchivedPost.postStatus).toBe('COMPLETED')
  expect(resp.data.restoreArchivedPost.image).toBeTruthy()

  // check we see that post in the feed and in the posts
  resp = await ourClient.query({query: queries.selfFeed})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.feed.items).toHaveLength(1)
  expect(resp.data.self.feed.items[0].postId).toBe(postId)
  expect(resp.data.self.feed.items[0].imageUploadUrl).toBeNull()
  expect(resp.data.self.feed.items[0].image.url).toBeTruthy()

  resp = await ourClient.query({query: queries.userPosts, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.posts.items).toHaveLength(1)
  expect(resp.data.user.posts.items[0].postId).toBe(postId)

  // post should not be visible when specifically requesting archived posts
  resp = await ourClient.query({query: queries.userPosts, variables: {userId: ourUserId, postStatus: 'ARCHIVED'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.posts.items).toHaveLength(0)
})

test('Attempts to restore invalid posts', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // verify can't restore a post that doens't exist
  await expect(
    ourClient.mutate({
      mutation: mutations.restoreArchivedPost,
      variables: {postId},
    }),
  ).rejects.toThrow('does not exist')

  // create a post
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)

  // verify can't restore that non-archived post
  await expect(
    ourClient.mutate({
      mutation: mutations.restoreArchivedPost,
      variables: {postId},
    }),
  ).rejects.toThrow('is not archived')

  // archive the post
  resp = await ourClient.mutate({mutation: mutations.archivePost, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.archivePost.postStatus).toBe('ARCHIVED')

  // verify another user can't restore our archived our post
  const [theirClient] = await loginCache.getCleanLogin()
  await expect(
    theirClient.mutate({
      mutation: mutations.restoreArchivedPost,
      variables: {postId},
    }),
  ).rejects.toThrow("another User's post")

  // verify we can restore our archvied post
  resp = await ourClient.mutate({mutation: mutations.restoreArchivedPost, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.restoreArchivedPost.postStatus).toBe('COMPLETED')
})

test('Post count reacts to user archiving posts', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // verify count starts at zero
  let resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.postCount).toBe(0)

  // add image post with direct image data upload, verify post count goes up immediately
  let postId = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postedBy.postCount).toBe(1)
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.postCount).toBe(1)

  // add a image post, verify count doesn't go up until the image is uploaded
  postId = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('PENDING')
  expect(resp.data.addPost.postedBy.postCount).toBe(1) // count has not incremented
  const uploadUrl = resp.data.addPost.imageUploadUrl
  await rp.put({url: uploadUrl, headers: imageHeaders, body: imageBytes})
  await misc.sleepUntilPostCompleted(ourClient, postId)

  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postStatus).toBe('COMPLETED')
  expect(resp.data.post.postedBy.postCount).toBe(2) // count has incremented
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.postCount).toBe(2)

  // archive that post, verify count goes down
  resp = await ourClient.mutate({mutation: mutations.archivePost, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.archivePost.postId).toBe(postId)
  expect(resp.data.archivePost.postStatus).toBe('ARCHIVED')
  expect(resp.data.archivePost.postedBy.postCount).toBe(1)
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.postCount).toBe(1)

  // cant test an expiring post is removed from the count yet,
  // because that is done in a cron-like job
  // add a way for the test suite to artificially trigger that job?
})

test('Cant archive a post that is not ours', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // they add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await theirClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // verify we cannot archive that post for them
  await expect(
    ourClient.mutate({
      mutation: mutations.archivePost,
      variables: {postId},
    }),
  ).rejects.toThrow("Cannot archive another User's post")
})

test('When a post is archived, any likes of it disappear', async () => {
  // us and them, they add a post
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await theirClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()

  // we onymously like it
  resp = await ourClient.mutate({mutation: mutations.onymouslyLikePost, variables: {postId}})
  expect(resp.errors).toBeUndefined()

  // they anonymously like it
  resp = await theirClient.mutate({mutation: mutations.anonymouslyLikePost, variables: {postId}})
  expect(resp.errors).toBeUndefined()

  // verify the post is now in the like lists
  resp = await theirClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.onymouslyLikedBy.items).toHaveLength(1)
  expect(resp.data.post.onymouslyLikedBy.items[0].userId).toBe(ourUserId)

  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.onymouslyLikedPosts.items).toHaveLength(1)
  expect(resp.data.self.onymouslyLikedPosts.items[0].postId).toBe(postId)

  resp = await theirClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.anonymouslyLikedPosts.items).toHaveLength(1)
  expect(resp.data.self.anonymouslyLikedPosts.items[0].postId).toBe(postId)

  // archive the post
  resp = await theirClient.mutate({mutation: mutations.archivePost, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.archivePost.postStatus).toBe('ARCHIVED')

  // clear our cache
  await ourClient.resetStore()

  // verify we can no longer see the post
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post).toBeNull()

  // verify the post has disappeared from the like lists
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.onymouslyLikedPosts.items).toHaveLength(0)

  resp = await theirClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.anonymouslyLikedPosts.items).toHaveLength(0)
})
