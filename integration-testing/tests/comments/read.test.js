const {v4: uuidv4} = require('uuid')

const {cognito, eventually, generateRandomJpeg} = require('../../utils')
const {mutations, queries} = require('../../schema')

const imageBytes = generateRandomJpeg(8, 8)
const imageData = new Buffer.from(imageBytes).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('One user adds multiple comments, ordering', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.commentsCount).toBe(0)
  expect(resp.data.addPost.comments.items).toHaveLength(0)

  // we add a comment on the post
  const commentId1 = uuidv4()
  variables = {commentId: commentId1, postId, text: 'lore'}
  resp = await ourClient.mutate({mutation: mutations.addComment, variables})
  expect(resp.data.addComment.commentId).toBe(commentId1)

  // we add another comment on the post
  const commentId2 = uuidv4()
  variables = {commentId: commentId2, postId, text: 'ipsum'}
  resp = await ourClient.mutate({mutation: mutations.addComment, variables})
  expect(resp.data.addComment.commentId).toBe(commentId2)

  // check we see both comments, in order, on the post
  const post = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.commentsCount).toBe(2)
    expect(data.post.comments.items).toHaveLength(2)
    expect(data.post.comments.items[0].commentId).toBe(commentId1)
    expect(data.post.comments.items[0].commentedBy.userId).toBe(ourUserId)
    expect(data.post.comments.items[1].commentId).toBe(commentId2)
    expect(data.post.comments.items[1].commentedBy.userId).toBe(ourUserId)
    return data.post
  })

  // verify we can supply the default value of reverse and get the same thing
  resp = await ourClient.query({query: queries.post, variables: {postId, commentsReverse: false}})
  expect(resp.data.post.comments).toEqual(post.comments)

  // check we can reverse the order of those comments
  resp = await ourClient.query({query: queries.post, variables: {postId, commentsReverse: true}})
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.commentsCount).toBe(2)
  expect(resp.data.post.comments.items).toHaveLength(2)
  expect(resp.data.post.comments.items[0].commentId).toBe(commentId2)
  expect(resp.data.post.comments.items[0].commentedBy.userId).toBe(ourUserId)
  expect(resp.data.post.comments.items[1].commentId).toBe(commentId1)
  expect(resp.data.post.comments.items[1].commentedBy.userId).toBe(ourUserId)
})

test('Comment viewed status reacts to views Post correctly', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}}).then((resp) => {
    expect(resp.data.addPost.postId).toBe(postId)
    expect(resp.data.addPost.commentsCount).toBe(0)
    expect(resp.data.addPost.comments.items).toHaveLength(0)
  })

  // they add a comment on the post
  const commentId1 = uuidv4()
  await theirClient
    .mutate({mutation: mutations.addComment, variables: {commentId: commentId1, postId, text: 'lore'}})
    .then((resp) => {
      expect(resp.data.addComment.commentId).toBe(commentId1)
      expect(resp.data.addComment.viewedStatus).toBe('VIEWED')
    })

  // they add another comment on the post
  const commentId2 = uuidv4()
  await theirClient
    .mutate({mutation: mutations.addComment, variables: {commentId: commentId2, postId, text: 'lore'}})
    .then((resp) => {
      expect(resp.data.addComment.commentId).toBe(commentId2)
      expect(resp.data.addComment.viewedStatus).toBe('VIEWED')
    })

  // check we see the comments correctly
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.comments.items).toHaveLength(2)
    expect(data.post.comments.items[0].commentId).toBe(commentId1)
    expect(data.post.comments.items[0].viewedStatus).toBe('NOT_VIEWED')
    expect(data.post.comments.items[1].commentId).toBe(commentId2)
    expect(data.post.comments.items[1].viewedStatus).toBe('NOT_VIEWED')
  })

  // we report to have viewed the post
  await ourClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId]}})

  // check we see the comments correctly
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.comments.items).toHaveLength(2)
    expect(data.post.comments.items[0].commentId).toBe(commentId1)
    expect(data.post.comments.items[0].viewedStatus).toBe('VIEWED')
    expect(data.post.comments.items[1].commentId).toBe(commentId2)
    expect(data.post.comments.items[1].viewedStatus).toBe('VIEWED')
  })

  // we add a comment to the post
  const commentId3 = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addComment, variables: {commentId: commentId3, postId, text: 'lore'}})
    .then((resp) => {
      expect(resp.data.addComment.commentId).toBe(commentId3)
      expect(resp.data.addComment.viewedStatus).toBe('VIEWED')
    })

  // they add another comment on the post
  const commentId4 = uuidv4()
  await theirClient
    .mutate({mutation: mutations.addComment, variables: {commentId: commentId4, postId, text: 'lore'}})
    .then((resp) => {
      expect(resp.data.addComment.commentId).toBe(commentId4)
      expect(resp.data.addComment.viewedStatus).toBe('VIEWED')
    })

  // check we see the comments correctly
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.comments.items).toHaveLength(4)
    expect(data.post.comments.items[0].commentId).toBe(commentId1)
    expect(data.post.comments.items[0].viewedStatus).toBe('VIEWED')
    expect(data.post.comments.items[1].commentId).toBe(commentId2)
    expect(data.post.comments.items[1].viewedStatus).toBe('VIEWED')
    expect(data.post.comments.items[2].commentId).toBe(commentId3)
    expect(data.post.comments.items[2].viewedStatus).toBe('VIEWED')
    expect(data.post.comments.items[3].commentId).toBe(commentId4)
    expect(data.post.comments.items[3].viewedStatus).toBe('NOT_VIEWED')
  })

  // we report to have viewed the post again
  await ourClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId]}})

  // check we see the comments correctly
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.comments.items).toHaveLength(4)
    expect(data.post.comments.items[0].commentId).toBe(commentId1)
    expect(data.post.comments.items[0].viewedStatus).toBe('VIEWED')
    expect(data.post.comments.items[1].commentId).toBe(commentId2)
    expect(data.post.comments.items[1].viewedStatus).toBe('VIEWED')
    expect(data.post.comments.items[2].commentId).toBe(commentId3)
    expect(data.post.comments.items[2].viewedStatus).toBe('VIEWED')
    expect(data.post.comments.items[3].commentId).toBe(commentId4)
    expect(data.post.comments.items[3].viewedStatus).toBe('VIEWED')
  })
})

test('Comments of private user on public post are visible to all', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // they go private
  let variables = {privacyStatus: 'PRIVATE'}
  let resp = await theirClient.mutate({mutation: mutations.setUserPrivacyStatus, variables})
  expect(resp.data.setUserDetails.userId).toBe(theirUserId)
  expect(resp.data.setUserDetails.privacyStatus).toBe('PRIVATE')

  // we add a post
  const postId = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postedBy.userId).toBe(ourUserId)

  // they comment on our post
  let commentId = uuidv4()
  resp = await theirClient.mutate({mutation: mutations.addComment, variables: {commentId, postId, text: 'lore'}})
  expect(resp.data.addComment.commentId).toBe(commentId)
  expect(resp.data.addComment.commentedBy.userId).toBe(theirUserId)

  // check we can see their comment on the post
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.commentsCount).toBe(1)
    expect(data.post.comments.items).toHaveLength(1)
    expect(data.post.comments.items[0].commentId).toBe(commentId)
    expect(data.post.comments.items[0].commentedBy.userId).toBe(theirUserId)
  })
})
