const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito')
const misc = require('../../utils/misc')
const {mutations, queries} = require('../../schema')

let anonClient
const imageBytes = misc.generateRandomJpeg(8, 8)
const imageData = new Buffer.from(imageBytes).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()
jest.retryTimes(1)

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())
afterEach(async () => {
  if (anonClient) await anonClient.mutate({mutation: mutations.deleteUser})
  anonClient = null
})

test('Add a comment with bad word', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  await ourClient.mutate({mutation: mutations.addPost, variables}).then(({data: {addPost: post}}) => {
    expect(post.postId).toBe(postId)
    expect(post.commentCount).toBe(0)
    expect(post.commentsCount).toBe(0)
    expect(post.comments.items).toHaveLength(0)
  })

  // we comment on the post
  const ourCommentId = uuidv4()
  const ourText = 'nice post'
  variables = {commentId: ourCommentId, postId, text: ourText}
  await ourClient.mutate({mutation: mutations.addComment, variables}).then(({data: {addComment: comment}}) => {
    expect(comment.commentId).toBe(ourCommentId)
  })

  // check we can see that comment
  await misc.sleep(1000)
  await ourClient.query({query: queries.post, variables: {postId}}).then(({data: {post}}) => {
    expect(post.postId).toBe(postId)
    expect(post.commentCount).toBe(1)
    expect(post.commentsCount).toBe(1)
    expect(post.comments.items).toHaveLength(1)
    expect(post.comments.items[0].commentId).toBe(ourCommentId)
    expect(post.comments.items[0].commentedBy.userId).toBe(ourUserId)
    expect(post.comments.items[0].text).toBe(ourText)
  })

  // they comment on the post with bad word, verify comment is removed
  const theirCommentId = uuidv4()
  const theirText = 'lore ipsum skype'
  variables = {commentId: theirCommentId, postId, text: theirText}
  await theirClient.mutate({mutation: mutations.addComment, variables}).then(({data: {addComment: comment}}) => {
    expect(comment.commentId).toBe(theirCommentId)
  })

  // check we see only our comment
  await misc.sleep(2000)
  await ourClient.query({query: queries.post, variables: {postId}}).then(({data: {post}}) => {
    expect(post.postId).toBe(postId)
    expect(post.commentCount).toBe(1)
    expect(post.commentsCount).toBe(1)
    expect(post.comments.items).toHaveLength(1)
    expect(post.comments.items[0].commentId).toBe(ourCommentId)
    expect(post.comments.items[0].commentedBy.userId).toBe(ourUserId)
    expect(post.comments.items[0].text).toBe(ourText)
  })
})
