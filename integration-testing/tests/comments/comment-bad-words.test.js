const {v4: uuidv4} = require('uuid')

const {cognito, eventually, generateRandomJpeg} = require('../../utils')
const {mutations, queries} = require('../../schema')

let anonClient
const imageBytes = generateRandomJpeg(8, 8)
const imageData = new Buffer.from(imageBytes).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()

// https://github.com/real-social-media/bad_words/blob/master/bucket/bad_words.json
const badWord = 'uoiFZP8bjS'

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
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.commentsCount).toBe(1)
    expect(data.post.comments.items).toHaveLength(1)
    expect(data.post.comments.items[0].commentId).toBe(ourCommentId)
    expect(data.post.comments.items[0].commentedBy.userId).toBe(ourUserId)
    expect(data.post.comments.items[0].text).toBe(ourText)
  })

  // they comment on the post with bad word, verify comment is removed
  let theirCommentId = uuidv4()
  let theirText = `lore ipsum ${badWord}`
  variables = {commentId: theirCommentId, postId, text: theirText}
  await theirClient.mutate({mutation: mutations.addComment, variables}).then(({data: {addComment: comment}}) => {
    expect(comment.commentId).toBe(theirCommentId)
  })

  theirCommentId = uuidv4()
  theirText = `lore ipsum ${badWord.toLowerCase()}`
  variables = {commentId: theirCommentId, postId, text: theirText}
  await theirClient.mutate({mutation: mutations.addComment, variables}).then(({data: {addComment: comment}}) => {
    expect(comment.commentId).toBe(theirCommentId)
  })

  // check we see only our comment
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.commentsCount).toBe(1)
    expect(data.post.comments.items).toHaveLength(1)
    expect(data.post.comments.items[0].commentId).toBe(ourCommentId)
    expect(data.post.comments.items[0].commentedBy.userId).toBe(ourUserId)
    expect(data.post.comments.items[0].text).toBe(ourText)
  })
})

test('Two way follow, skip bad word detection', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  await ourClient.mutate({mutation: mutations.addPost, variables}).then(({data: {addPost: post}}) => {
    expect(post.postId).toBe(postId)
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
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.commentsCount).toBe(1)
    expect(data.post.comments.items).toHaveLength(1)
    expect(data.post.comments.items[0].commentId).toBe(ourCommentId)
    expect(data.post.comments.items[0].commentedBy.userId).toBe(ourUserId)
    expect(data.post.comments.items[0].text).toBe(ourText)
  })

  // they follow us
  await theirClient
    .mutate({mutation: mutations.followUser, variables: {userId: ourUserId}})
    .then(({data}) => expect(data.followUser.followedStatus).toBe('FOLLOWING'))

  // we follow them
  await ourClient
    .mutate({mutation: mutations.followUser, variables: {userId: theirUserId}})
    .then(({data}) => expect(data.followUser.followedStatus).toBe('FOLLOWING'))

  // make sure dynamo's gsi's have caught up
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.followedUsers.items).toHaveLength(1)
    expect(data.self.followerUsers.items).toHaveLength(1)
  })
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.self})
    expect(data.self.followedUsers.items).toHaveLength(1)
    expect(data.self.followerUsers.items).toHaveLength(1)
  })

  // they comment on the post with bad word, verify comment is added
  const theirCommentId = uuidv4()
  const theirText = `lore ipsum ${badWord}`
  variables = {commentId: theirCommentId, postId, text: theirText}
  await theirClient.mutate({mutation: mutations.addComment, variables}).then(({data: {addComment: comment}}) => {
    expect(comment.commentId).toBe(theirCommentId)
  })

  // check we see all comments
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.commentsCount).toBe(2)
    expect(data.post.comments.items).toHaveLength(2)
    expect(data.post.comments.items[0].commentId).toBe(ourCommentId)
    expect(data.post.comments.items[1].commentId).toBe(theirCommentId)
    expect(data.post.comments.items[1].commentedBy.userId).toBe(theirUserId)
    expect(data.post.comments.items[1].text).toBe(theirText)
  })
})
