/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const schema = require('../../utils/schema.js')

const imageData = misc.generateRandomJpeg(8, 8)
const imageDataB64 = new Buffer.from(imageData).toString('base64')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('When we stop following a private user, any likes of ours on their posts disappear', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we follow them
  let resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')

  // they go private
  resp = await theirClient.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['privacyStatus']).toBe('PRIVATE')

  // they add two posts
  const [postId1, postId2] = [uuidv4(), uuidv4()]
  let variables = {postId: postId1, mediaId: uuidv4(), imageData: imageDataB64}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  variables = {postId: postId2, mediaId: uuidv4(), imageData: imageDataB64}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()

  // we like the first post onymously
  resp = await ourClient.mutate({mutation: schema.onymouslyLikePost, variables: {postId: postId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['onymouslyLikePost']['postId']).toBe(postId1)
  expect(resp['data']['onymouslyLikePost']['likeStatus']).toBe('ONYMOUSLY_LIKED')

  // we like the second post anonymously
  resp = await ourClient.mutate({mutation: schema.anonymouslyLikePost, variables: {postId: postId2}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['anonymouslyLikePost']['postId']).toBe(postId2)
  expect(resp['data']['anonymouslyLikePost']['likeStatus']).toBe('ANONYMOUSLY_LIKED')

  // check those likes show up in the lists
  resp = await ourClient.query({query: schema.post, variables: {postId: postId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['onymouslyLikedBy']['items']).toHaveLength(1)
  expect(resp['data']['post']['onymouslyLikedBy']['items'][0]['userId']).toBe(ourUserId)

  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['onymouslyLikedPosts']['items']).toHaveLength(1)
  expect(resp['data']['self']['onymouslyLikedPosts']['items'][0]['postId']).toBe(postId1)

  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['anonymouslyLikedPosts']['items']).toHaveLength(1)
  expect(resp['data']['self']['anonymouslyLikedPosts']['items'][0]['postId']).toBe(postId2)

  // we stop following the user
  resp = await ourClient.mutate({mutation: schema.unfollowUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['unfollowUser']['followedStatus']).toBe('NOT_FOLLOWING')

  // clear our cache
  await ourClient.resetStore()

  // check those likes disappeared from the lists
  resp = await ourClient.query({query: schema.post, variables: {postId: postId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']).toBeNull()  // access denied

  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['onymouslyLikedPosts']['items']).toHaveLength(0)

  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['anonymouslyLikedPosts']['items']).toHaveLength(0)
})


test('When a private user decides to deny our following, any likes of ours on their posts disappear', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we follow them
  let resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')

  // they go private
  resp = await theirClient.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['privacyStatus']).toBe('PRIVATE')

  // they add two posts
  const [postId1, postId2] = [uuidv4(), uuidv4()]
  let variables = {postId: postId1, mediaId: uuidv4(), imageData: imageDataB64}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  variables = {postId: postId2, mediaId: uuidv4(), imageData: imageDataB64}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()

  // we like the first post onymously
  resp = await ourClient.mutate({mutation: schema.onymouslyLikePost, variables: {postId: postId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['onymouslyLikePost']['postId']).toBe(postId1)
  expect(resp['data']['onymouslyLikePost']['likeStatus']).toBe('ONYMOUSLY_LIKED')

  // we like the second post anonymously
  resp = await ourClient.mutate({mutation: schema.anonymouslyLikePost, variables: {postId: postId2}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['anonymouslyLikePost']['postId']).toBe(postId2)
  expect(resp['data']['anonymouslyLikePost']['likeStatus']).toBe('ANONYMOUSLY_LIKED')

  // check those likes show up in the lists
  resp = await ourClient.query({query: schema.post, variables: {postId: postId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['onymouslyLikedBy']['items']).toHaveLength(1)
  expect(resp['data']['post']['onymouslyLikedBy']['items'][0]['userId']).toBe(ourUserId)

  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['onymouslyLikedPosts']['items']).toHaveLength(1)
  expect(resp['data']['self']['onymouslyLikedPosts']['items'][0]['postId']).toBe(postId1)

  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['anonymouslyLikedPosts']['items']).toHaveLength(1)
  expect(resp['data']['self']['anonymouslyLikedPosts']['items'][0]['postId']).toBe(postId2)

  // now they deny our following
  resp = await theirClient.mutate({mutation: schema.denyFollowerUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['denyFollowerUser']['followerStatus']).toBe('DENIED')

  // reset our cache
  await ourClient.resetStore()

  // check we can no longer see lists of likes
  resp = await ourClient.query({query: schema.post, variables: {postId: postId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']).toBeNull()  // access denied

  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['onymouslyLikedPosts']['items']).toHaveLength(0)

  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['anonymouslyLikedPosts']['items']).toHaveLength(0)
})
