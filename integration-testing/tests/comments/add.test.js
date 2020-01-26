/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const schema = require('../../utils/schema.js')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Add a comments', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, text: 'lore ipsum'}
  let resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['commentCount']).toBe(0)
  expect(resp['data']['addPost']['comments']['items']).toHaveLength(0)

  // we comment on the post
  const ourCommentId = uuidv4()
  const ourText = 'nice post'
  variables = {commentId: ourCommentId, postId, text: ourText}
  resp = await ourClient.mutate({mutation: schema.addComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addComment']['commentId']).toBe(ourCommentId)

  // check we can see that comment
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['commentCount']).toBe(1)
  expect(resp['data']['post']['comments']['items']).toHaveLength(1)
  expect(resp['data']['post']['comments']['items'][0]['commentId']).toBe(ourCommentId)
  expect(resp['data']['post']['comments']['items'][0]['commentedBy']['userId']).toBe(ourUserId)
  expect(resp['data']['post']['comments']['items'][0]['text']).toBe(ourText)

  // they comment on the post
  const theirCommentId = uuidv4()
  const theirText = 'lore ipsum'
  variables = {commentId: theirCommentId, postId, text: theirText}
  resp = await theirClient.mutate({mutation: schema.addComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addComment']['commentId']).toBe(theirCommentId)

  // check we see both comments, in order, on the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['commentCount']).toBe(2)
  expect(resp['data']['post']['comments']['items']).toHaveLength(2)
  expect(resp['data']['post']['comments']['items'][0]['commentId']).toBe(ourCommentId)
  expect(resp['data']['post']['comments']['items'][1]['commentId']).toBe(theirCommentId)
  expect(resp['data']['post']['comments']['items'][1]['commentedBy']['userId']).toBe(theirUserId)
  expect(resp['data']['post']['comments']['items'][1]['text']).toBe(theirText)
})


test('Verify commentIds cannot be re-used ', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, text: 'lore ipsum'}
  let resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // they comment on the post
  const commentId = uuidv4()
  variables = {commentId, postId, text: 'nice lore'}
  resp = await theirClient.mutate({mutation: schema.addComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addComment']['commentId']).toBe(commentId)

  // check we cannot add another comment re-using that commentId
  variables = {commentId, postId, text: 'i agree'}
  await expect(ourClient.mutate({mutation: schema.addComment, variables})).rejects.toThrow()
})


test('Cant add comments to post that doesnt exist', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  let variables = {commentId: uuidv4(), postId: 'dne-post-id', text: 'no way'}
  await expect(ourClient.mutate({mutation: schema.addComment, variables})).rejects.toThrow()
})


test('Cant add comments to post with comments disabled', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post with comments disabled
  const postId = uuidv4()
  let variables = {postId, text: 'lore ipsum', commentsDisabled: true}
  let resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['commentsDisabled']).toBe(true)

  // check they cannot comment on the post
  variables = {commentId: uuidv4(), postId, text: 'no way'}
  await expect(theirClient.mutate({mutation: schema.addComment, variables})).rejects.toThrow()
})


test('Cant add comments to a post of a user that has blocked us, or a user we have blocked', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // they block us
  let variables = {userId: ourUserId}
  let resp = await theirClient.mutate({mutation: schema.blockUser, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(ourUserId)
  expect(resp['data']['blockUser']['blockedAt']).toBeTruthy()
  expect(resp['data']['blockUser']['blockedStatus']).toBe('BLOCKING')

  // they add a post
  const theirPostId = uuidv4()
  variables = {postId: theirPostId, text: 'lore ipsum'}
  resp = await theirClient.mutate({mutation: schema.addTextOnlyPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(theirPostId)

  // we add a post
  const ourPostId = uuidv4()
  variables = {postId: ourPostId, text: 'lore ipsum'}
  resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(ourPostId)

  // check we cannot comment on their post
  variables = {commentId: uuidv4(), postId: theirPostId, text: 'no way'}
  await expect(ourClient.mutate({mutation: schema.addComment, variables})).rejects.toThrow()

  // check they cannot comment on our post
  variables = {commentId: uuidv4(), postId: ourPostId, text: 'no way'}
  await expect(theirClient.mutate({mutation: schema.addComment, variables})).rejects.toThrow()
})


test('Cant add comments to a post of a private user unless were following them', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // they go private
  let variables = {privacyStatus: 'PRIVATE'}
  let resp = await theirClient.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()

  // they add a post
  const postId = uuidv4()
  variables = {postId, text: 'lore ipsum'}
  resp = await theirClient.mutate({mutation: schema.addTextOnlyPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // check we cannot comment on the post
  variables = {commentId: uuidv4(), postId, text: 'no way'}
  await expect(ourClient.mutate({mutation: schema.addComment, variables})).rejects.toThrow()

  // we request to follow them
  variables = {userId: theirUserId}
  resp = await ourClient.mutate({mutation: schema.followUser, variables})
  expect(resp['errors']).toBeUndefined()

  // check we cannot comment on the post
  variables = {commentId: uuidv4(), postId, text: 'no way'}
  await expect(ourClient.mutate({mutation: schema.addComment, variables})).rejects.toThrow()

  // they accept our follow request
  variables = {userId: ourUserId}
  resp = await theirClient.mutate({mutation: schema.acceptFollowerUser, variables})
  expect(resp['errors']).toBeUndefined()

  // check we _can_ comment on the post
  const commentId = uuidv4()
  variables = {commentId, postId, text: 'nice lore'}
  resp = await ourClient.mutate({mutation: schema.addComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addComment']['commentId']).toBe(commentId)

  // they change their mind and now deny our following
  variables = {userId: ourUserId}
  resp = await theirClient.mutate({mutation: schema.denyFollowerUser, variables})
  expect(resp['errors']).toBeUndefined()

  // check we cannot comment on the post
  variables = {commentId: uuidv4(), postId, text: 'no way'}
  await expect(ourClient.mutate({mutation: schema.addComment, variables})).rejects.toThrow()
})
