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


test('Anybody can flag post of public user', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, mediaId: uuidv4(), imageData: imageDataB64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // they flag that post
  resp = await theirClient.mutate({mutation: schema.flagPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['flagPost']['postId']).toBe(postId)
})


test('Follower can flag post of private user', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, mediaId: uuidv4(), imageData: imageDataB64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // they follow us
  resp = await theirClient.mutate({mutation: schema.followUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()

  // we go private
  resp = await ourClient.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()

  // they flag that post
  resp = await theirClient.mutate({mutation: schema.flagPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['flagPost']['postId']).toBe(postId)
})


test('Non-follower cannot flag post of private user', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, mediaId: uuidv4(), imageData: imageDataB64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // we go private
  resp = await ourClient.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()

  // they try to flag that post
  await expect(theirClient.mutate({mutation: schema.flagPost, variables: {postId}})).rejects.toBeDefined()
})


test('Cannot flag post that does not exist', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // try to flag a non-existent post
  const postId = uuidv4()
  await expect(ourClient.mutate({mutation: schema.flagPost, variables: {postId}})).rejects.toBeDefined()
})


test('Post.flagStatus changes correctly when post is flagged', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, mediaId: uuidv4(), imageData: imageDataB64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // check the post is not already flagged
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['flagStatus']).toBe('NOT_FLAGGED')

  // flag the post
  resp = await ourClient.mutate({mutation: schema.flagPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['flagPost']['postId']).toBe(postId)
  expect(resp['data']['flagPost']['flagStatus']).toBe('FLAGGED')

  // double check that was saved
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['flagStatus']).toBe('FLAGGED')
})


test('Cannot double-flag a post', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, mediaId: uuidv4(), imageData: imageDataB64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // flag the post
  resp = await ourClient.mutate({mutation: schema.flagPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()

  // try to flag it a second time
  await expect(ourClient.mutate({mutation: schema.flagPost, variables: {postId}})).rejects.toBeDefined()
})


test('Cannot flag post of user that has blocked us', async () => {
  // us and them
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // they add a post
  const postId = uuidv4()
  let variables = {postId, mediaId: uuidv4(), imageData: imageDataB64}
  let resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()

  // they block us
  resp = await theirClient.mutate({mutation: schema.blockUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we cannot flag their post
  await expect(ourClient.mutate({mutation: schema.flagPost, variables: {postId}})).rejects.toBeDefined()

  // they unblock us
  resp = await theirClient.mutate({mutation: schema.unblockUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we can flag their post
  resp = await ourClient.mutate({mutation: schema.flagPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['flagPost']['flagStatus']).toBe('FLAGGED')
})


test('Cannot flag post of user we have blocked', async () => {
  // us and them
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // they add a post
  const postId = uuidv4()
  let variables = {postId, mediaId: uuidv4(), imageData: imageDataB64}
  let resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()

  // we block them
  resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we cannot flag their post
  await expect(ourClient.mutate({mutation: schema.flagPost, variables: {postId}})).rejects.toBeDefined()

  // we unblock them
  resp = await ourClient.mutate({mutation: schema.unblockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we can flag their post
  resp = await ourClient.mutate({mutation: schema.flagPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['flagPost']['flagStatus']).toBe('FLAGGED')
})
