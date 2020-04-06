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


test('Cannot like/dislike posts with likes disabled', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post with likes disabled
  const postId = uuidv4()
  let variables = {postId, imageData, text: 'lore ipsum', likesDisabled: true}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['likesDisabled']).toBe(true)

  // verify we can't like the post
  variables = {postId}
  await expect(ourClient.mutate({mutation: schema.onymouslyLikePost, variables})).rejects.toThrow('ClientError')
  await expect(ourClient.mutate({mutation: schema.anonymouslyLikePost, variables})).rejects.toThrow('ClientError')

  // verify they can't like the post
  variables = {postId}
  await expect(theirClient.mutate({mutation: schema.onymouslyLikePost, variables})).rejects.toThrow('ClientError')
  await expect(theirClient.mutate({mutation: schema.anonymouslyLikePost, variables})).rejects.toThrow('ClientError')

  // verify no likes show up on the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['onymousLikeCount']).toBeNull()
  expect(resp['data']['post']['anonymousLikeCount']).toBeNull()
  expect(resp['data']['post']['onymouslyLikedBy']).toBeNull()
})


test('Likes preservered through period with posts likes disabled', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // we add a post with likes enabled
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['likesDisabled']).toBe(false)

  // we like the and they do too
  resp = await ourClient.mutate({mutation: schema.onymouslyLikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  resp = await theirClient.mutate({mutation: schema.anonymouslyLikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()

  // check we can see all of those likes on the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['onymousLikeCount']).toBe(1)
  expect(resp['data']['post']['anonymousLikeCount']).toBe(1)
  expect(resp['data']['post']['onymouslyLikedBy']['items']).toHaveLength(1)
  expect(resp['data']['post']['onymouslyLikedBy']['items'][0]['userId']).toBe(ourUserId)

  // now disable likes on the post
  resp = await ourClient.mutate({mutation: schema.editPost, variables: {postId, likesDisabled: true}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPost']['likesDisabled']).toBe(true)

  // verify we can't like the post
  variables = {postId}
  await expect(ourClient.mutate({mutation: schema.onymouslyLikePost, variables})).rejects.toThrow('ClientError')
  await expect(ourClient.mutate({mutation: schema.anonymouslyLikePost, variables})).rejects.toThrow('ClientError')

  // verify no likes show up on the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['onymousLikeCount']).toBeNull()
  expect(resp['data']['post']['anonymousLikeCount']).toBeNull()
  expect(resp['data']['post']['onymouslyLikedBy']).toBeNull()

  // now enable likes on the post
  resp = await ourClient.mutate({mutation: schema.editPost, variables: {postId, likesDisabled: false}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPost']['likesDisabled']).toBe(false)

  // verify the original likes now show up on the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['onymousLikeCount']).toBe(1)
  expect(resp['data']['post']['anonymousLikeCount']).toBe(1)
  expect(resp['data']['post']['onymouslyLikedBy']['items']).toHaveLength(1)
  expect(resp['data']['post']['onymouslyLikedBy']['items'][0]['userId']).toBe(ourUserId)
})


test('User disables likes, cannot like/dislike posts, nor can other users dislike/like their posts', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const ourPostId = uuidv4()
  let variables = {postId: ourPostId, imageData}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(ourPostId)

  // they add a post
  const theirPostId = uuidv4()
  variables = {postId: theirPostId, imageData}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(theirPostId)

  // we disable our likes
  resp = await ourClient.mutate({mutation: schema.setUserMentalHealthSettings, variables: {likesDisabled: true}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['likesDisabled']).toBe(true)

  // verify we can't like their post
  variables = {postId: theirPostId}
  await expect(ourClient.mutate({mutation: schema.onymouslyLikePost, variables})).rejects.toThrow('ClientError')
  await expect(ourClient.mutate({mutation: schema.anonymouslyLikePost, variables})).rejects.toThrow('ClientError')

  // verify they can't like our post
  variables = {postId: ourPostId}
  await expect(theirClient.mutate({mutation: schema.onymouslyLikePost, variables})).rejects.toThrow('ClientError')
  await expect(theirClient.mutate({mutation: schema.anonymouslyLikePost, variables})).rejects.toThrow('ClientError')

  // verify we *can't* see like counts on our own post
  variables = {postId: ourPostId}
  resp = await ourClient.query({query: schema.post, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(ourPostId)
  expect(resp['data']['post']['onymousLikeCount']).toBeNull()
  expect(resp['data']['post']['anonymousLikeCount']).toBeNull()
  expect(resp['data']['post']['onymouslyLikedBy']).toBeNull()

  // verify we *can't* see like counts on their post
  variables = {postId: theirPostId}
  resp = await ourClient.query({query: schema.post, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(theirPostId)
  expect(resp['data']['post']['onymousLikeCount']).toBeNull()
  expect(resp['data']['post']['anonymousLikeCount']).toBeNull()
  expect(resp['data']['post']['onymouslyLikedBy']).toBeNull()

  // verify they *cannot* see like counts on our post
  variables = {postId: ourPostId}
  resp = await theirClient.query({query: schema.post, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(ourPostId)
  expect(resp['data']['post']['onymousLikeCount']).toBeNull()
  expect(resp['data']['post']['anonymousLikeCount']).toBeNull()
  expect(resp['data']['post']['onymouslyLikedBy']).toBeNull()

  // verify they *can* see like counts on their post
  variables = {postId: theirPostId}
  resp = await theirClient.query({query: schema.post, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(theirPostId)
  expect(resp['data']['post']['onymousLikeCount']).toBe(0)
  expect(resp['data']['post']['anonymousLikeCount']).toBe(0)
  expect(resp['data']['post']['onymouslyLikedBy']['items']).toHaveLength(0)
})


test('Verify likes preserved through period in which user disables their likes', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // we add a post
  const variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['likesDisabled']).toBe(false)

  // we like the and they do too
  resp = await ourClient.mutate({mutation: schema.onymouslyLikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  resp = await theirClient.mutate({mutation: schema.anonymouslyLikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()

  // check we can see all of those likes on the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['onymousLikeCount']).toBe(1)
  expect(resp['data']['post']['anonymousLikeCount']).toBe(1)
  expect(resp['data']['post']['onymouslyLikedBy']['items']).toHaveLength(1)
  expect(resp['data']['post']['onymouslyLikedBy']['items'][0]['userId']).toBe(ourUserId)

  // now we disable likes
  resp = await ourClient.mutate({mutation: schema.setUserMentalHealthSettings, variables: {likesDisabled: true}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['likesDisabled']).toBe(true)

  // verify we cant see likes on the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['onymousLikeCount']).toBeNull()
  expect(resp['data']['post']['anonymousLikeCount']).toBeNull()
  expect(resp['data']['post']['onymouslyLikedBy']).toBeNull()

  // now we enable likes
  resp = await ourClient.mutate({mutation: schema.setUserMentalHealthSettings, variables: {likesDisabled: false}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['likesDisabled']).toBe(false)

  // verify the original likes now show up on the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['onymousLikeCount']).toBe(1)
  expect(resp['data']['post']['anonymousLikeCount']).toBe(1)
  expect(resp['data']['post']['onymouslyLikedBy']['items']).toHaveLength(1)
  expect(resp['data']['post']['onymouslyLikedBy']['items'][0]['userId']).toBe(ourUserId)
})
