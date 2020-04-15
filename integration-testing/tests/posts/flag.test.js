/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const { mutations, queries } = require('../../schema')

const imageBytes = misc.generateRandomJpeg(8, 8)
const imageData = new Buffer.from(imageBytes).toString('base64')

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
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // they flag that post
  resp = await theirClient.mutate({mutation: mutations.flagPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['flagPost']['postId']).toBe(postId)
})


test('Follower can flag post of private user', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // they follow us
  resp = await theirClient.mutate({mutation: mutations.followUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()

  // we go private
  resp = await ourClient.mutate({mutation: mutations.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()

  // they flag that post
  resp = await theirClient.mutate({mutation: mutations.flagPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['flagPost']['postId']).toBe(postId)
})


test('Non-follower cannot flag post of private user', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // we go private
  resp = await ourClient.mutate({mutation: mutations.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()

  // they try to flag that post
  await expect(theirClient.mutate({mutation: mutations.flagPost, variables: {postId}}))
    .rejects.toThrow('ClientError')
})


test('Cannot flag post that does not exist', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // try to flag a non-existent post
  const postId = uuidv4()
  await expect(ourClient.mutate({mutation: mutations.flagPost, variables: {postId}})).rejects.toThrow('ClientError')
})


test('Post.flagStatus changes correctly when post is flagged', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // check the post is not already flagged
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['flagStatus']).toBe('NOT_FLAGGED')

  // flag the post
  resp = await ourClient.mutate({mutation: mutations.flagPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['flagPost']['postId']).toBe(postId)
  expect(resp['data']['flagPost']['flagStatus']).toBe('FLAGGED')

  // double check that was saved
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['flagStatus']).toBe('FLAGGED')
})


test('Cannot double-flag a post', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // flag the post
  resp = await ourClient.mutate({mutation: mutations.flagPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()

  // try to flag it a second time
  await expect(ourClient.mutate({mutation: mutations.flagPost, variables: {postId}})).rejects.toThrow('ClientError')
})


test('Cannot flag post of user that has blocked us', async () => {
  // us and them
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // they add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await theirClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()

  // they block us
  resp = await theirClient.mutate({mutation: mutations.blockUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we cannot flag their post
  await expect(ourClient.mutate({mutation: mutations.flagPost, variables: {postId}})).rejects.toThrow('ClientError')

  // they unblock us
  resp = await theirClient.mutate({mutation: mutations.unblockUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we can flag their post
  resp = await ourClient.mutate({mutation: mutations.flagPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['flagPost']['flagStatus']).toBe('FLAGGED')
})


test('Cannot flag post of user we have blocked', async () => {
  // us and them
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // they add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await theirClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()

  // we block them
  resp = await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we cannot flag their post
  await expect(ourClient.mutate({mutation: mutations.flagPost, variables: {postId}})).rejects.toThrow('ClientError')

  // we unblock them
  resp = await ourClient.mutate({mutation: mutations.unblockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we can flag their post
  resp = await ourClient.mutate({mutation: mutations.flagPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['flagPost']['flagStatus']).toBe('FLAGGED')
})
