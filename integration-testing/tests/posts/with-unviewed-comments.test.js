const {v4: uuidv4} = require('uuid')

const {cognito, eventually, sleep} = require('../../utils')
const {mutations, queries} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Privacy', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // check we can see our own
  await ourClient.query({query: queries.self}).then(({data, errors}) => {
    expect(errors).toBeUndefined()
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.postsWithUnviewedComments.items).toHaveLength(0)
  })

  // check we can see our own
  await ourClient.query({query: queries.user, variables: {userId: ourUserId}}).then(({data, errors}) => {
    expect(errors).toBeUndefined()
    expect(data.user.userId).toBe(ourUserId)
    expect(data.user.postsWithUnviewedComments.items).toHaveLength(0)
  })

  // check they cannot see ours
  await theirClient.query({query: queries.user, variables: {userId: ourUserId}}).then(({data, errors}) => {
    expect(errors).toBeUndefined()
    expect(data.user.userId).toBe(ourUserId)
    expect(data.user.postsWithUnviewedComments).toBeNull()
  })

  // they add a post
  const postId = uuidv4()
  await theirClient
    .mutate({mutation: mutations.addPost, variables: {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'}})
    .then(({data, errors}) => {
      expect(errors).toBeUndefined()
      expect(data.addPost.postId).toBe(postId)
      expect(data.addPost.postStatus).toBe('COMPLETED')
    })

  // we comment on it
  await ourClient
    .mutate({mutation: mutations.addComment, variables: {commentId: uuidv4(), postId, text: 'lore'}})
    .then(({data, errors}) => {
      expect(errors).toBeUndefined()
      expect(data.addComment.commentId).toBeTruthy()
    })

  // check that we can't see their list
  await sleep()
  await ourClient.query({query: queries.user, variables: {userId: theirUserId}}).then(({data}) => {
    expect(data.user.userId).toBe(theirUserId)
    expect(data.user.postsWithUnviewedComments).toBeNull()
  })

  // check it doesn't show up in our list
  await ourClient.query({query: queries.self}).then(({data, errors}) => {
    expect(errors).toBeUndefined()
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.postsWithUnviewedComments.items).toHaveLength(0)
  })
})

test('Add and remove', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'}})
    .then(({data, errors}) => {
      expect(errors).toBeUndefined()
      expect(data.addPost.postId).toBe(postId)
      expect(data.addPost.postStatus).toBe('COMPLETED')
    })

  // check that post has no univewed comments
  await ourClient.query({query: queries.self}).then(({data, errors}) => {
    expect(errors).toBeUndefined()
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.postsWithUnviewedComments.items).toHaveLength(0)
  })

  // they comment on the post
  await theirClient
    .mutate({mutation: mutations.addComment, variables: {commentId: uuidv4(), postId, text: 'lore'}})
    .then(({data, errors}) => {
      expect(errors).toBeUndefined()
      expect(data.addComment.commentId).toBeTruthy()
    })

  // check that post now has unviewed comments
  await eventually(async () => {
    const {data, errors} = await ourClient.query({query: queries.self})
    expect(errors).toBeUndefined()
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.postsWithUnviewedComments.items).toHaveLength(1)
    expect(data.self.postsWithUnviewedComments.items[0].postId).toBe(postId)
  })

  // we report to have viewed the post
  await ourClient
    .mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId]}})
    .then(({data, errors}) => {
      expect(errors).toBeUndefined()
      expect(data.reportPostViews).toBe(true)
    })

  // check that post has no unviewed comments
  await eventually(async () => {
    const {data, errors} = await ourClient.query({query: queries.self})
    expect(errors).toBeUndefined()
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.postsWithUnviewedComments.items).toHaveLength(0)
  })
})

test('Order', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()

  // we add three posts
  const [postId1, postId2, postId3] = [uuidv4(), uuidv4(), uuidv4()]
  for (const postId of [postId1, postId2, postId3]) {
    await ourClient
      .mutate({mutation: mutations.addPost, variables: {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'}})
      .then(({data, errors}) => {
        expect(errors).toBeUndefined()
        expect(data.addPost.postId).toBe(postId)
        expect(data.addPost.postStatus).toBe('COMPLETED')
      })
  }

  // check no post has unviewed comments
  await ourClient.query({query: queries.self}).then(({data, errors}) => {
    expect(errors).toBeUndefined()
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.postsWithUnviewedComments.items).toHaveLength(0)
  })

  // they comment on the posts in an odd order
  for (const postId of [postId2, postId3, postId1]) {
    await theirClient
      .mutate({mutation: mutations.addComment, variables: {commentId: uuidv4(), postId, text: 'lore ipsum'}})
      .then(({data, errors}) => {
        expect(errors).toBeUndefined()
        expect(data.addComment.commentId).toBeTruthy()
      })
  }

  // pull our posts by unviewed comments, check the order is correct
  await eventually(async () => {
    const {data, errors} = await ourClient.query({query: queries.self})
    expect(errors).toBeUndefined()
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.postsWithUnviewedComments.items).toHaveLength(3)
    expect(data.self.postsWithUnviewedComments.items[0].postId).toBe(postId1)
    expect(data.self.postsWithUnviewedComments.items[1].postId).toBe(postId3)
    expect(data.self.postsWithUnviewedComments.items[2].postId).toBe(postId2)
  })
})
