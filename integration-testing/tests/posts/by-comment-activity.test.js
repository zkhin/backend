/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const {mutations, queries} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Privacy', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // check we can see our own
  let resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.postsByNewCommentActivity.items).toHaveLength(0)

  // check we can see our own
  resp = await ourClient.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.userId).toBe(ourUserId)
  expect(resp.data.user.postsByNewCommentActivity.items).toHaveLength(0)

  // check they cannot see ours
  resp = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.userId).toBe(ourUserId)
  expect(resp.data.user.postsByNewCommentActivity).toBeNull()

  // they add a post
  const postId = uuidv4()
  resp = await theirClient.mutate({
    mutation: mutations.addPost,
    variables: {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'},
  })
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // we comment on it
  const commentId = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addComment, variables: {commentId, postId, text: 'lore'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addComment.commentId).toBe(commentId)
  await misc.sleep(2000) // let dynamo converge

  // check that we can't see their list
  resp = await ourClient.query({query: queries.user, variables: {userId: theirUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.userId).toBe(theirUserId)
  expect(resp.data.user.postsByNewCommentActivity).toBeNull()

  // check it doesn't show up in our list
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.postsByNewCommentActivity.items).toHaveLength(0)
})

test('Add and remove', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let resp = await ourClient.mutate({
    mutation: mutations.addPost,
    variables: {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'},
  })
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // check that post has no comment activity
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.postsByNewCommentActivity.items).toHaveLength(0)

  // they comment on the post
  const commentId = uuidv4()
  resp = await theirClient.mutate({mutation: mutations.addComment, variables: {commentId, postId, text: 'lore'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addComment.commentId).toBe(commentId)
  await misc.sleep(2000) // let dynamo converge

  // check that post now has comment activity
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.postsByNewCommentActivity.items).toHaveLength(1)
  expect(resp.data.self.postsByNewCommentActivity.items[0].postId).toBe(postId)

  // we report to have read that comment
  resp = await ourClient.mutate({mutation: mutations.reportCommentViews, variables: {commentIds: [commentId]}})
  expect(resp.errors).toBeUndefined()
  await misc.sleep(2000) // let dynamo converge

  // check that post has no comment activity
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.postsByNewCommentActivity.items).toHaveLength(0)
})

test('Order', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add three posts
  const [postId1, postId2, postId3] = [uuidv4(), uuidv4(), uuidv4()]
  const postType = 'TEXT_ONLY'
  for (const postId of [postId1, postId2, postId3]) {
    const resp = await ourClient.mutate({
      mutation: mutations.addPost,
      variables: {postId, postType, text: 'lore ipsum'},
    })
    expect(resp.errors).toBeUndefined()
    expect(resp.data.addPost.postId).toBe(postId)
    expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  }

  // check no post has comment activity
  let resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.postsByNewCommentActivity.items).toHaveLength(0)

  // they comment on the posts in an odd order
  for (const postId of [postId2, postId3, postId1]) {
    const commentId = uuidv4()
    const resp = await theirClient.mutate({
      mutation: mutations.addComment,
      variables: {commentId, postId, text: 'lore ipsum'},
    })
    expect(resp.errors).toBeUndefined()
    expect(resp.data.addComment.commentId).toBe(commentId)
  }
  await misc.sleep(2000) // let dynamo converge

  // pull our comments by activity, check the order is correct
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.postsByNewCommentActivity.items).toHaveLength(3)
  expect(resp.data.self.postsByNewCommentActivity.items[0].postId).toBe(postId1)
  expect(resp.data.self.postsByNewCommentActivity.items[1].postId).toBe(postId3)
  expect(resp.data.self.postsByNewCommentActivity.items[2].postId).toBe(postId2)
})
