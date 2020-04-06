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


test('Post owner comment activity does not change Post.hasNewCommentActivity', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['hasNewCommentActivity']).toBe(false)

  // we comment on the post
  const commentId = uuidv4()
  variables = {commentId, postId, text: 'lore? ipsum!'}
  resp = await ourClient.mutate({mutation: schema.addComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addComment']['commentId']).toBe(commentId)

  // check there is no new comment activity on the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['hasNewCommentActivity']).toBe(false)

  // check there is no new comment activity for the user
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postHasNewCommentActivity']).toBe(false)

  // delete the comment
  resp = await ourClient.mutate({mutation: schema.deleteComment, variables: {commentId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['deleteComment']['commentId']).toBe(commentId)

  // check there is no new comment activity on the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['hasNewCommentActivity']).toBe(false)

  // check there is no new comment activity for the user
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postHasNewCommentActivity']).toBe(false)
})


test('Post.hasNewCommentActivity - set, reset, privacy', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['hasNewCommentActivity']).toBe(false)

  // check they cannot see Post.hasNewCommentActivity not User.postHasNewCommentActivity
  resp = await theirClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['hasNewCommentActivity']).toBeNull()
  expect(resp['data']['post']['postedBy']['postHasNewCommentActivity']).toBeNull()

  // they comment on the post twice
  const commentId1 = uuidv4()
  variables = {commentId: commentId1, postId, text: 'lore? ip!'}
  resp = await theirClient.mutate({mutation: schema.addComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addComment']['commentId']).toBe(commentId1)

  const commentId2 = uuidv4()
  variables = {commentId: commentId2, postId, text: 'lore? ip!'}
  resp = await theirClient.mutate({mutation: schema.addComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addComment']['commentId']).toBe(commentId2)

  // check there is new comment activity on the post, user
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['hasNewCommentActivity']).toBe(true)
  expect(resp['data']['post']['postedBy']['postHasNewCommentActivity']).toBe(true)

  // we report to have viewed one comment, the first one
  resp = await ourClient.mutate({mutation: schema.reportCommentViews, variables: {commentIds: [commentId1]}})
  expect(resp['errors']).toBeUndefined()

  // check there is now *no* new comment activity on the post & user
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['hasNewCommentActivity']).toBe(false)
  expect(resp['data']['post']['postedBy']['postHasNewCommentActivity']).toBe(false)

  // they delete the comment, the one we haven't viewed
  resp = await theirClient.mutate({mutation: schema.deleteComment, variables: {commentId: commentId2}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['deleteComment']['commentId']).toBe(commentId2)

  // check there is new comment activity on the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['hasNewCommentActivity']).toBe(true)
  expect(resp['data']['post']['postedBy']['postHasNewCommentActivity']).toBe(true)

  // we report to have viewed comment that was no deleted, again
  resp = await ourClient.mutate({mutation: schema.reportCommentViews, variables: {commentIds: [commentId1]}})
  expect(resp['errors']).toBeUndefined()

  // check there is now *no* new comment activity on the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['hasNewCommentActivity']).toBe(false)
  expect(resp['data']['post']['postedBy']['postHasNewCommentActivity']).toBe(false)

  // we delete a comment, the one we viewed
  resp = await ourClient.mutate({mutation: schema.deleteComment, variables: {commentId: commentId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['deleteComment']['commentId']).toBe(commentId1)

  // check there is no new comment activity on the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['hasNewCommentActivity']).toBe(false)
  expect(resp['data']['post']['postedBy']['postHasNewCommentActivity']).toBe(false)
})


test('User.postHasNewCommentActivity - set, reset, privacy', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId1 = uuidv4()
  let variables = {postId: postId1, postType: 'TEXT_ONLY', text: 'lore ipsum'}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)

  // we add another post
  const postId2 = uuidv4()
  variables = {postId: postId2, postType: 'TEXT_ONLY', text: 'lore ipsum'}
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)

  // check we have no comment activity
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postHasNewCommentActivity']).toBe(false)

  // check they cannot see our comment activity
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['postHasNewCommentActivity']).toBeNull()

  // they add two comments to the first post
  const commentId11 = uuidv4()
  variables = {commentId: commentId11, postId: postId1, text: 'lore? ip!'}
  resp = await theirClient.mutate({mutation: schema.addComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addComment']['commentId']).toBe(commentId11)

  const commentId12 = uuidv4()
  variables = {commentId: commentId12, postId: postId1, text: 'lore? ip!'}
  resp = await theirClient.mutate({mutation: schema.addComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addComment']['commentId']).toBe(commentId12)

  // they add one comment to the second post
  const commentId22 = uuidv4()
  variables = {commentId: commentId22, postId: postId2, text: 'lore? ip!'}
  resp = await theirClient.mutate({mutation: schema.addComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addComment']['commentId']).toBe(commentId22)

  // check we have comment activity
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postHasNewCommentActivity']).toBe(true)

  // check they still cannot see our comment activity
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['postHasNewCommentActivity']).toBeNull()

  // we read the comment on the second post
  resp = await ourClient.mutate({mutation: schema.reportCommentViews, variables: {commentIds: [commentId22]}})
  expect(resp['errors']).toBeUndefined()

  // check we still have comment activity (from the other post)
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postHasNewCommentActivity']).toBe(true)

  // we read one of the two comments on the second post
  resp = await ourClient.mutate({mutation: schema.reportCommentViews, variables: {commentIds: [commentId11]}})
  expect(resp['errors']).toBeUndefined()

  // check we no longer have comment activity
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postHasNewCommentActivity']).toBe(false)
})
