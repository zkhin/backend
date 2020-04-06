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


test('Delete comments', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['commentCount']).toBe(0)
  expect(resp['data']['addPost']['comments']['items']).toHaveLength(0)

  // they comment on the post
  const theirCommentId = uuidv4()
  variables = {commentId: theirCommentId, postId, text: 'lore'}
  resp = await theirClient.mutate({mutation: schema.addComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addComment']['commentId']).toBe(theirCommentId)

  // we comment on the post
  const ourCommentId = uuidv4()
  variables = {commentId: ourCommentId, postId, text: 'ipsum'}
  resp = await ourClient.mutate({mutation: schema.addComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addComment']['commentId']).toBe(ourCommentId)

  // check we see both comments, in order, on the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['commentCount']).toBe(2)
  expect(resp['data']['post']['comments']['items']).toHaveLength(2)
  expect(resp['data']['post']['comments']['items'][0]['commentId']).toBe(theirCommentId)
  expect(resp['data']['post']['comments']['items'][1]['commentId']).toBe(ourCommentId)

  // they delete their comment
  variables = {commentId: theirCommentId}
  resp = await theirClient.mutate({mutation: schema.deleteComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['deleteComment']['commentId']).toBe(theirCommentId)

  // check we only see one comment on the post now
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['commentCount']).toBe(1)
  expect(resp['data']['post']['comments']['items']).toHaveLength(1)
  expect(resp['data']['post']['comments']['items'][0]['commentId']).toBe(ourCommentId)

  // we delete our comment
  variables = {commentId: ourCommentId}
  resp = await ourClient.mutate({mutation: schema.deleteComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['deleteComment']['commentId']).toBe(ourCommentId)

  // check no comments appear on the post now
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['commentCount']).toBe(0)
  expect(resp['data']['post']['comments']['items']).toHaveLength(0)
})


test('Delete someone elses comment on our post', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['commentCount']).toBe(0)
  expect(resp['data']['addPost']['comments']['items']).toHaveLength(0)

  // they comment on the post
  const theirCommentId = uuidv4()
  variables = {commentId: theirCommentId, postId, text: 'lore'}
  resp = await theirClient.mutate({mutation: schema.addComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addComment']['commentId']).toBe(theirCommentId)

  // check we can see that comment on the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['commentCount']).toBe(1)
  expect(resp['data']['post']['comments']['items']).toHaveLength(1)
  expect(resp['data']['post']['comments']['items'][0]['commentId']).toBe(theirCommentId)

  // we delete their comment
  variables = {commentId: theirCommentId}
  resp = await ourClient.mutate({mutation: schema.deleteComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['deleteComment']['commentId']).toBe(theirCommentId)

  // check no comments appear on the post now
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['commentCount']).toBe(0)
  expect(resp['data']['post']['comments']['items']).toHaveLength(0)
})


test('Cant delete a comment that doesnt exist', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  let variables = {commentId: uuidv4()}
  await expect(ourClient.mutate({mutation: schema.deleteComment, variables})).rejects.toThrow()
})


test('Cant delete someone elses comment on someone elses post', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // they add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['commentCount']).toBe(0)
  expect(resp['data']['addPost']['comments']['items']).toHaveLength(0)

  // they comment on the post
  const theirCommentId = uuidv4()
  variables = {commentId: theirCommentId, postId, text: 'lore'}
  resp = await theirClient.mutate({mutation: schema.addComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addComment']['commentId']).toBe(theirCommentId)

  // verify we can't delete their comment
  variables = {commentId: theirCommentId}
  await expect(ourClient.mutate({mutation: schema.deleteComment, variables})).rejects.toThrow()

  // check they can see that comment on the post
  resp = await theirClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['commentCount']).toBe(1)
  expect(resp['data']['post']['comments']['items']).toHaveLength(1)
  expect(resp['data']['post']['comments']['items'][0]['commentId']).toBe(theirCommentId)
})


test('Can delete comments even if we have comments disabled and the post has comments disabled', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['commentCount']).toBe(0)
  expect(resp['data']['addPost']['comments']['items']).toHaveLength(0)

  // we comment on the post
  const ourCommentId = uuidv4()
  variables = {commentId: ourCommentId, postId, text: 'lore'}
  resp = await ourClient.mutate({mutation: schema.addComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addComment']['commentId']).toBe(ourCommentId)

  // we disable comments for our user
  variables = {commentsDisabled: true}
  resp = await ourClient.mutate({mutation: schema.setUserMentalHealthSettings, variables})

  // verify we can see that comment on the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['commentCount']).toBe(1)
  expect(resp['data']['post']['comments']['items']).toHaveLength(1)
  expect(resp['data']['post']['comments']['items'][0]['commentId']).toBe(ourCommentId)

  // we disable comments on the post
  variables = {postId, commentsDisabled: true}
  resp = await ourClient.mutate({mutation: schema.editPost, variables})
  expect(resp['errors']).toBeUndefined()

  // verify we can't see comments on post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['commentCount']).toBeNull()
  expect(resp['data']['post']['comments']).toBeNull()

  // but we can still delete the comment
  variables = {commentId: ourCommentId}
  resp = await ourClient.mutate({mutation: schema.deleteComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['deleteComment']['commentId']).toBe(ourCommentId)

  // we enable comments on the post
  variables = {postId, commentsDisabled: false}
  resp = await ourClient.mutate({mutation: schema.editPost, variables})
  expect(resp['errors']).toBeUndefined()

  // verify the comment has disappeared from the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['commentCount']).toBe(0)
  expect(resp['data']['post']['comments']['items']).toHaveLength(0)
})
