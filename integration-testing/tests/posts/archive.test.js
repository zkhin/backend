/* eslint-env jest */

const fs = require('fs')
const path = require('path')
const rp = require('request-promise-native')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const schema = require('../../utils/schema.js')

const imageData = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg'))
const imageDataB64 = new Buffer.from(imageData).toString('base64')
const imageHeaders = {'Content-Type': 'image/jpeg'}

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Archiving an image post', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // we uplaod an image post
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId, imageData: imageDataB64}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId)

  // check we see that post in the feed, in the posts, and in the mediaObjects
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(1)
  expect(resp['data']['self']['feed']['items'][0]['postId']).toBe(postId)
  expect(resp['data']['self']['feed']['items'][0]['image']['url']).not.toBeNull()
  expect(resp['data']['self']['feed']['items'][0]['imageUploadUrl']).toBeNull()
  expect(resp['data']['self']['feed']['items'][0]['mediaObjects']).toHaveLength(1)
  expect(resp['data']['self']['feed']['items'][0]['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(resp['data']['self']['feed']['items'][0]['mediaObjects'][0]['url']).not.toBeNull()
  expect(resp['data']['self']['feed']['items'][0]['mediaObjects'][0]['uploadUrl']).toBeNull()

  resp = await ourClient.query({query: schema.userPosts, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toHaveLength(1)
  expect(resp['data']['user']['posts']['items'][0]['postId']).toBe(postId)

  resp = await ourClient.query({query: schema.userMediaObjects, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toHaveLength(1)
  expect(resp['data']['user']['mediaObjects']['items'][0]['mediaId']).toBe(mediaId)

  // archive the post
  resp = await ourClient.mutate({mutation: schema.archivePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['archivePost']['postStatus']).toBe('ARCHIVED')
  expect(resp['data']['archivePost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['archivePost']['mediaObjects'][0]['mediaStatus']).toBe('ARCHIVED')

  // post and media should be gone from the normal queries - feed, posts, mediaObjects
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(0)

  resp = await ourClient.query({query: schema.userPosts, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toHaveLength(0)

  resp = await ourClient.query({query: schema.userMediaObjects, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toHaveLength(0)

  // post and media should be visible when specifically requesting archived posts
  resp = await ourClient.query({query: schema.userPosts, variables: {userId: ourUserId, postStatus: 'ARCHIVED'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toHaveLength(1)
  expect(resp['data']['user']['posts']['items'][0]['postId']).toBe(postId)

  resp = await ourClient.query({
    query: schema.userMediaObjects,
    variables: {userId: ourUserId, mediaStatus: 'ARCHIVED'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toHaveLength(1)
  expect(resp['data']['user']['mediaObjects']['items'][0]['mediaId']).toBe(mediaId)
})


test('Cant archive a post in PENDING status', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we create a post, leave it with pending status
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postStatus']).toBe('PENDING')
  expect(resp['data']['addPost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId)

  // verify we can't archive that post
  await expect(ourClient.mutate({mutation: schema.archivePost, variables: {postId}})).rejects.toThrow('ClientError')
})


test('Archiving an image post does not affect media urls', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // we uplaod an image post
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId, imageData: imageDataB64}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId)
  const image = resp['data']['addPost']['image']
  expect(image['url']).toBeTruthy()

  // check the urls are as we expect
  resp = await ourClient.query({
    query: schema.userMediaObjects,
    variables: {userId: ourUserId, mediaStatus: 'UPLOADED'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toHaveLength(1)
  expect(resp['data']['user']['mediaObjects']['items'][0]['mediaId']).toBe(mediaId)
  expect(resp['data']['user']['mediaObjects']['items'][0]['url']).toBeTruthy()
  expect(resp['data']['user']['mediaObjects']['items'][0]['url64p']).toBeTruthy()
  expect(resp['data']['user']['mediaObjects']['items'][0]['url480p']).toBeTruthy()
  expect(resp['data']['user']['mediaObjects']['items'][0]['url1080p']).toBeTruthy()
  expect(resp['data']['user']['mediaObjects']['items'][0]['url4k']).toBeTruthy()
  expect(resp['data']['user']['mediaObjects']['items'][0]['uploadUrl']).toBeNull()

  // archive the post
  resp = await ourClient.mutate({mutation: schema.archivePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['archivePost']['postStatus']).toBe('ARCHIVED')
  expect(resp['data']['archivePost']['imageUploadUrl']).toBeNull()
  expect(resp['data']['archivePost']['image']['url']).toBeTruthy()
  expect(resp['data']['archivePost']['image']['url']).toBeTruthy()
  expect(resp['data']['archivePost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['archivePost']['mediaObjects'][0]['mediaStatus']).toBe('ARCHIVED')
  expect(resp['data']['archivePost']['mediaObjects'][0]['url']).toBeTruthy()
  expect(resp['data']['archivePost']['mediaObjects'][0]['url64p']).toBeTruthy()
  expect(resp['data']['archivePost']['mediaObjects'][0]['url480p']).toBeTruthy()
  expect(resp['data']['archivePost']['mediaObjects'][0]['url1080p']).toBeTruthy()
  expect(resp['data']['archivePost']['mediaObjects'][0]['url4k']).toBeTruthy()
  expect(resp['data']['archivePost']['mediaObjects'][0]['uploadUrl']).toBeNull()

  // check the url haven't changed
  resp = await ourClient.query({
    query: schema.userMediaObjects,
    variables: {userId: ourUserId, mediaStatus: 'ARCHIVED'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toHaveLength(1)
  expect(resp['data']['user']['mediaObjects']['items'][0]['mediaId']).toBe(mediaId)
  expect(resp['data']['user']['mediaObjects']['items'][0]['url']).toBeTruthy()
  expect(resp['data']['user']['mediaObjects']['items'][0]['url64p']).toBeTruthy()
  expect(resp['data']['user']['mediaObjects']['items'][0]['url480p']).toBeTruthy()
  expect(resp['data']['user']['mediaObjects']['items'][0]['url1080p']).toBeTruthy()
  expect(resp['data']['user']['mediaObjects']['items'][0]['url4k']).toBeTruthy()
  expect(resp['data']['user']['mediaObjects']['items'][0]['uploadUrl']).toBeNull()

  // check the url bases have not changed
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['postStatus']).toBe('ARCHIVED')
  const newImage = resp['data']['post']['image']
  expect(image['url'].split('?')[0]).toBe(newImage['url'].split('?')[0])
  expect(image['url4k'].split('?')[0]).toBe(newImage['url4k'].split('?')[0])
  expect(image['url1080p'].split('?')[0]).toBe(newImage['url1080p'].split('?')[0])
  expect(image['url480p'].split('?')[0]).toBe(newImage['url480p'].split('?')[0])
  expect(image['url64p'].split('?')[0]).toBe(newImage['url64p'].split('?')[0])
})


test('Restoring an archived image post', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // we uplaod an image post
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId, imageData: imageDataB64}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId)

  // archive the post
  resp = await ourClient.mutate({mutation: schema.archivePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['archivePost']['postStatus']).toBe('ARCHIVED')
  expect(resp['data']['archivePost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['archivePost']['mediaObjects'][0]['mediaStatus']).toBe('ARCHIVED')

  // restore the post
  resp = await ourClient.mutate({mutation: schema.restoreArchivedPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['restoreArchivedPost']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['restoreArchivedPost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['restoreArchivedPost']['mediaObjects'][0]['mediaStatus']).toBe('UPLOADED')

  // check we see that post in the feed, in the posts, and in the mediaObjects
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(1)
  expect(resp['data']['self']['feed']['items'][0]['postId']).toBe(postId)
  expect(resp['data']['self']['feed']['items'][0]['imageUploadUrl']).toBeNull()
  expect(resp['data']['self']['feed']['items'][0]['image']['url']).not.toBeNull()
  expect(resp['data']['self']['feed']['items'][0]['mediaObjects']).toHaveLength(1)
  expect(resp['data']['self']['feed']['items'][0]['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(resp['data']['self']['feed']['items'][0]['mediaObjects'][0]['url']).not.toBeNull()
  expect(resp['data']['self']['feed']['items'][0]['mediaObjects'][0]['uploadUrl']).toBeNull()

  resp = await ourClient.query({query: schema.userPosts, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toHaveLength(1)
  expect(resp['data']['user']['posts']['items'][0]['postId']).toBe(postId)

  resp = await ourClient.query({query: schema.userMediaObjects, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toHaveLength(1)
  expect(resp['data']['user']['mediaObjects']['items'][0]['mediaId']).toBe(mediaId)

  // post and media should not be visible when specifically requesting archived posts
  resp = await ourClient.query({query: schema.userPosts, variables: {userId: ourUserId, postStatus: 'ARCHIVED'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toHaveLength(0)

  resp = await ourClient.query({
    query: schema.userMediaObjects,
    variables: {userId: ourUserId, mediaStatus: 'ARCHIVED'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toHaveLength(0)
})


test('Attempts to restore invalid posts', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // verify can't restore a post that doens't exist
  await expect(ourClient.mutate({
    mutation: schema.restoreArchivedPost,
    variables: {postId},
  })).rejects.toThrow('does not exist')

  // create a post
  let variables = {postId, mediaId: uuidv4(), imageData: imageDataB64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // verify can't restore that non-archived post
  await expect(ourClient.mutate({
    mutation: schema.restoreArchivedPost,
    variables: {postId},
  })).rejects.toThrow('is not archived')

  // archive the post
  resp = await ourClient.mutate({mutation: schema.archivePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['archivePost']['postStatus']).toBe('ARCHIVED')

  // verify another user can't restore our archived our post
  const [theirClient] = await loginCache.getCleanLogin()
  await expect(theirClient.mutate({
    mutation: schema.restoreArchivedPost,
    variables: {postId},
  })).rejects.toThrow("another User's post")

  // verify we can restore our archvied post
  resp = await ourClient.mutate({mutation: schema.restoreArchivedPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['restoreArchivedPost']['postStatus']).toBe('COMPLETED')
})


test('Post count reacts to user archiving posts', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // verify count starts at zero
  let resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postCount']).toBe(0)

  // add media post with direct image data upload, verify post count goes up immediately
  let [postId, mediaId] = [uuidv4(), uuidv4()]
  resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId, imageData: imageDataB64}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postedBy']['postCount']).toBe(1)
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postCount']).toBe(1)

  // add a media post, verify count doesn't go up until the media is uploaded
  ;[postId, mediaId] = [uuidv4(), uuidv4()]
  resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postStatus']).toBe('PENDING')
  expect(resp['data']['addPost']['postedBy']['postCount']).toBe(1)  // count has not incremented
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId)
  const uploadUrl = resp['data']['addPost']['imageUploadUrl']
  expect(uploadUrl.split('?')[0]).toBe(resp['data']['addPost']['mediaObjects'][0]['uploadUrl'].split('?')[0])
  await rp.put({url: uploadUrl, headers: imageHeaders, body: imageData})
  await misc.sleepUntilPostCompleted(ourClient, postId)

  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['post']['postedBy']['postCount']).toBe(2) // count has incremented
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postCount']).toBe(2)

  // archive that post, verify count goes down
  resp = await ourClient.mutate({mutation: schema.archivePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['archivePost']['postId']).toBe(postId)
  expect(resp['data']['archivePost']['postStatus']).toBe('ARCHIVED')
  expect(resp['data']['archivePost']['postedBy']['postCount']).toBe(1)
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postCount']).toBe(1)

  // cant test an expiring post is removed from the count yet,
  // because that is done in a cron-like job
  // add a way for the test suite to artificially trigger that job?
})


test('Cant archive a post that is not ours', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // they add a post
  const postId = uuidv4()
  let variables = {postId, mediaId: uuidv4(), imageData: imageDataB64}
  let resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')

  // verify we cannot archive that post for them
  await expect(ourClient.mutate({
    mutation: schema.archivePost,
    variables: {postId},
  })).rejects.toThrow("Cannot archive another User's post")
})


test('When a post is archived, any likes of it disappear', async () => {
  // us and them, they add a post
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()
  let variables = {postId, mediaId: uuidv4(), imageData: imageDataB64}
  let resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()

  // we onymously like it
  resp = await ourClient.mutate({mutation: schema.onymouslyLikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()

  // they anonymously like it
  resp = await theirClient.mutate({mutation: schema.anonymouslyLikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()

  // verify the post is now in the like lists
  resp = await theirClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['onymouslyLikedBy']['items']).toHaveLength(1)
  expect(resp['data']['post']['onymouslyLikedBy']['items'][0]['userId']).toBe(ourUserId)

  resp = await ourClient.query({query: schema.self })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['onymouslyLikedPosts']['items']).toHaveLength(1)
  expect(resp['data']['self']['onymouslyLikedPosts']['items'][0]['postId']).toBe(postId)

  resp = await theirClient.query({query: schema.self })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['anonymouslyLikedPosts']['items']).toHaveLength(1)
  expect(resp['data']['self']['anonymouslyLikedPosts']['items'][0]['postId']).toBe(postId)

  // archive the post
  resp = await theirClient.mutate({mutation: schema.archivePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['archivePost']['postStatus']).toBe('ARCHIVED')

  // clear our cache
  await ourClient.resetStore()

  // verify we can no longer see the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']).toBeNull()

  // verify the post has disappeared from the like lists
  resp = await ourClient.query({query: schema.self })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['onymouslyLikedPosts']['items']).toHaveLength(0)

  resp = await theirClient.query({query: schema.self })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['anonymouslyLikedPosts']['items']).toHaveLength(0)
})
