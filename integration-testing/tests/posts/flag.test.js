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


test('Cant flag our own post', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['flagStatus']).toBe('NOT_FLAGGED')

  // verify we cant flag that post
  await expect(ourClient.mutate({mutation: mutations.flagPost, variables: {postId}}))
    .rejects.toThrow(/ClientError: .* their own post /)

  // check we did not flag the post is not flagged
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['flagStatus']).toBe('NOT_FLAGGED')
})



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


test('Cant flag a post if we are disabled', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // they add a post
  const postId = uuidv4()
  let resp = await theirClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // we disable ourselves
  resp = await ourClient.mutate({mutation: mutations.disableUser})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['disableUser']['userId']).toBe(ourUserId)
  expect(resp['data']['disableUser']['userStatus']).toBe('DISABLED')

  // verify we can't flag their post
  await expect(ourClient.mutate({mutation: mutations.flagPost, variables: {postId}}))
    .rejects.toThrow(/ClientError: User .* is not ACTIVE/)
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
    .rejects.toThrow(/ClientError: .* does not have access to post/)
})


test('Cannot flag post that does not exist', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // try to flag a non-existent post
  const postId = uuidv4()
  await expect(ourClient.mutate({mutation: mutations.flagPost, variables: {postId}}))
    .rejects.toThrow(/ClientError: Post .* does not exist/)
})


test('Post.flagStatus changes correctly when post is flagged', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // check they have not flagged the post
  resp = await theirClient.query({query: queries.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['flagStatus']).toBe('NOT_FLAGGED')

  // they flag the post
  resp = await theirClient.mutate({mutation: mutations.flagPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['flagPost']['postId']).toBe(postId)
  expect(resp['data']['flagPost']['flagStatus']).toBe('FLAGGED')

  // double check that was saved
  resp = await theirClient.query({query: queries.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['flagStatus']).toBe('FLAGGED')
})


test('Cannot double-flag a post', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // they flag the post
  resp = await theirClient.mutate({mutation: mutations.flagPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()

  // try to flag it a second time
  await expect(theirClient.mutate({mutation: mutations.flagPost, variables: {postId}}))
    .rejects.toThrow(/ClientError: .* has already been flagged /)
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
  await expect(ourClient.mutate({mutation: mutations.flagPost, variables: {postId}}))
    .rejects.toThrow(/ClientError: .* has been blocked by owner /)

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
  await expect(ourClient.mutate({mutation: mutations.flagPost, variables: {postId}}))
    .rejects.toThrow(/ClientError: .* has blocked owner /)

  // we unblock them
  resp = await ourClient.mutate({mutation: mutations.unblockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we can flag their post
  resp = await ourClient.mutate({mutation: mutations.flagPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['flagPost']['flagStatus']).toBe('FLAGGED')
})
