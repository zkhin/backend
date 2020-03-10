/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const schema = require('../../utils/schema.js')

const imageBytes = misc.generateRandomJpeg(8, 8)
const imageData = new Buffer.from(imageBytes).toString('base64')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Delete a post that was our next story to expire', async () => {
  // us, them, they follow us
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()
  let resp = await theirClient.mutate({mutation: schema.followUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')

  // we create a post
  const postId = uuidv4()
  let variables = {postId, mediaId: uuidv4(), imageData, lifetime: 'PT1H'}
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // verify we see that post
  resp = await ourClient.query({query: schema.userPosts, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toHaveLength(1)
  expect(resp['data']['user']['posts']['items'][0]['postId']).toBe(postId)

  // verify we see it as a story
  resp = await ourClient.query({query: schema.userStories, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']['items']).toHaveLength(1)
  expect(resp['data']['user']['stories']['items'][0]['postId']).toBe(postId)

  // verify our post count reacted
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postCount']).toBe(1)

  // verify it showed up in their feed
  resp = await theirClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(1)
  expect(resp['data']['self']['feed']['items'][0]['postId']).toBe(postId)

  // verify we show up in the first followed users list
  resp = await theirClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followedUsersWithStories']['items']).toHaveLength(1)
  expect(resp['data']['self']['followedUsersWithStories']['items'][0]['userId']).toBe(ourUserId)

  // delete the post
  resp = await ourClient.mutate({mutation: schema.deletePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['deletePost']['postStatus']).toBe('DELETING')

  // verify we cannot see that post
  resp = await ourClient.query({query: schema.userPosts, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toHaveLength(0)
  resp = await ourClient.query({query: schema.userPosts, variables: {userId: ourUserId, postStatus: 'DELETING'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toHaveLength(0)

  // verify we cannot see it as a story
  resp = await ourClient.query({query: schema.userStories, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']['items']).toHaveLength(0)

  // verify our post count reacted
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postCount']).toBe(0)

  // verify it disappeared from their feed
  resp = await theirClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(0)

  // verify we do not show up in the first followed users list
  resp = await theirClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followedUsersWithStories']['items']).toHaveLength(0)
})


test('Deleting post with media', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // we create an image post
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId)

  // verify we can see the post & media object
  resp = await ourClient.query({query: schema.userPosts, variables: {userId: ourUserId, postStatus: 'PENDING'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toHaveLength(1)
  expect(resp['data']['user']['posts']['items'][0]['postId']).toBe(postId)
  resp = await ourClient.query({
    query: schema.userMediaObjects,
    variables: {userId: ourUserId, mediaStatus: 'AWAITING_UPLOAD'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toHaveLength(1)
  expect(resp['data']['user']['mediaObjects']['items'][0]['mediaId']).toBe(mediaId)

  // delete the post
  resp = await ourClient.mutate({mutation: schema.deletePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['deletePost']['postStatus']).toBe('DELETING')
  expect(resp['data']['deletePost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['deletePost']['mediaObjects'][0]['mediaStatus']).toBe('DELETING')

  // verify we can no longer see the post or media object
  resp = await ourClient.query({query: schema.userPosts, variables: {userId: ourUserId, postStatus: 'PENDING'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toHaveLength(0)
  resp = await ourClient.query({query: schema.userPosts, variables: {userId: ourUserId, postStatus: 'DELETING'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toHaveLength(0)
  resp = await ourClient.query({
    query: schema.userMediaObjects,
    variables: {userId: ourUserId, mediaStatus: 'AWAITING_UPLOAD'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toHaveLength(0)
  resp = await ourClient.query({
    query: schema.userMediaObjects,
    variables: {userId: ourUserId, mediaStatus: 'DELETING'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toHaveLength(0)
})


test('Invalid attempts to delete posts', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // verify can't delete post that doens't exist
  await expect(ourClient.mutate({mutation: schema.deletePost, variables: {postId}})).rejects.toThrow('not exist')

  // create a post
  let resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId: uuidv4()}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // verify another user can't delete our post
  const [theirClient] = await loginCache.getCleanLogin()
  await expect(theirClient.mutate({
    mutation: schema.deletePost,
    variables: {postId},
  })).rejects.toThrow("another User's post")

  // verify we can actually delete that post
  resp = await ourClient.mutate({mutation: schema.deletePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['deletePost']['postStatus']).toBe('DELETING')
})


test('When a post is deleted, any likes of it disappear', async () => {
  // us and them, they add a post
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()
  let variables = {postId, mediaId: uuidv4(), imageData}
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

  // delete the post
  resp = await theirClient.mutate({mutation: schema.deletePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['deletePost']['postStatus']).toBe('DELETING')

  // clear our cache
  await ourClient.resetStore()

  // verify the post has disappeared from the like lists
  resp = await ourClient.query({query: schema.self })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['onymouslyLikedPosts']['items']).toHaveLength(0)

  resp = await theirClient.query({query: schema.self })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['anonymouslyLikedPosts']['items']).toHaveLength(0)
})
