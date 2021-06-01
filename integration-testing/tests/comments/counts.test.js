import {v4 as uuidv4} from 'uuid'

import {cognito, eventually, sleep} from '../../utils'
import {mutations, queries} from '../../schema'

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Only post owner can use viewedStatus with Post.commentsCount, others see null', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'}})
    .then(({data}) => expect(data.addPost.postId).toBe(postId))

  // check we see viewed/unviewed comment counts
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.commentsCount).toBe(0)
    expect(data.post.commentsViewedCount).toBe(0)
    expect(data.post.commentsUnviewedCount).toBe(0)
  })

  // check they do not see viewed/unviewed comment counts
  await theirClient.query({query: queries.post, variables: {postId}}).then((resp) => {
    expect(resp.data.post.postId).toBe(postId)
    expect(resp.data.post.commentsCount).toBe(0)
    expect(resp.data.post.commentsViewedCount).toBeNull()
    expect(resp.data.post.commentsUnviewedCount).toBeNull()
  })
})

test('Adding comments: Post owners comments always viewed, others comments are unviewed', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'}})
    .then((resp) => {
      expect(resp.data.addPost.postId).toBe(postId)
    })

  // check starting state
  await ourClient.query({query: queries.post, variables: {postId}}).then((resp) => {
    expect(resp.data.post.postId).toBe(postId)
    expect(resp.data.post.commentsCount).toBe(0)
    expect(resp.data.post.commentsViewedCount).toBe(0)
    expect(resp.data.post.commentsUnviewedCount).toBe(0)
  })

  // we comment on the post
  await ourClient
    .mutate({mutation: mutations.addComment, variables: {commentId: uuidv4(), postId, text: 'lore? ipsum!'}})
    .then((resp) => {
      expect(resp.data.addComment.commentId).toBeTruthy()
    })

  // check that comment was counted viewed
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.commentsCount).toBe(1)
    expect(data.post.commentsViewedCount).toBe(1)
    expect(data.post.commentsUnviewedCount).toBe(0)
  })

  // they comment on the post
  await theirClient
    .mutate({mutation: mutations.addComment, variables: {commentId: uuidv4(), postId, text: 'lore? ipsum!'}})
    .then((resp) => {
      expect(resp.data.addComment.commentId).toBeTruthy()
    })

  // check that comment was counted unviewed
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.commentsCount).toBe(2)
    expect(data.post.commentsViewedCount).toBe(1)
    expect(data.post.commentsUnviewedCount).toBe(1)
  })
})

test('Viewing posts: Post owners views clear the unviewed comment counter, others dont', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'}})
    .then((resp) => expect(resp.data.addPost.postId).toBe(postId))

  // they comment on the post
  await theirClient
    .mutate({mutation: mutations.addComment, variables: {commentId: uuidv4(), postId, text: 'lore? ipsum!'}})
    .then((resp) => expect(resp.data.addComment.commentId).toBeTruthy())

  // check viewed/unviewed counts
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.commentsCount).toBe(1)
    expect(data.post.commentsViewedCount).toBe(0)
    expect(data.post.commentsUnviewedCount).toBe(1)
  })

  // they report a post view
  await theirClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId]}})

  // check viewed/unviewed counts - no change
  await sleep()
  await ourClient.query({query: queries.post, variables: {postId}}).then(({data}) => {
    expect(data.post.postId).toBe(postId)
    expect(data.post.commentsCount).toBe(1)
    expect(data.post.commentsViewedCount).toBe(0)
    expect(data.post.commentsUnviewedCount).toBe(1)
  })

  // we report a post view
  await ourClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId]}})

  // check viewed/unviewed counts - unviewed have become viewed
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.commentsCount).toBe(1)
    expect(data.post.commentsViewedCount).toBe(1)
    expect(data.post.commentsUnviewedCount).toBe(0)
  })

  // they comment on the post again
  await theirClient
    .mutate({mutation: mutations.addComment, variables: {commentId: uuidv4(), postId, text: 'lore? ipsum!'}})
    .then((resp) => expect(resp.data.addComment.commentId).toBeTruthy())

  // check viewed/unviewed counts - should have a new unviewed
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.commentsCount).toBe(2)
    expect(data.post.commentsViewedCount).toBe(1)
    expect(data.post.commentsUnviewedCount).toBe(1)
  })

  // we report a post view
  await ourClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId]}})

  // check viewed/unviewed counts - unviewed have become viewed again
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.commentsCount).toBe(2)
    expect(data.post.commentsViewedCount).toBe(2)
    expect(data.post.commentsUnviewedCount).toBe(0)
  })
})
