import {v4 as uuidv4} from 'uuid'

import {cognito, eventually, generateRandomJpeg, sleep} from '../../utils'
import {mutations, queries} from '../../schema'

let anonClient
const imageBytes = generateRandomJpeg(300, 200)
const imageData = new Buffer.from(imageBytes).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())
afterEach(async () => {
  if (anonClient) await anonClient.mutate({mutation: mutations.deleteUser})
  anonClient = null
})

test('Add post with keywords attribute', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  const [postId1, postId2, postId3, postId4] = [uuidv4(), uuidv4(), uuidv4(), uuidv4()]
  let keywords = ['mine', 'bird']

  // Add three posts
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId: postId1, imageData, keywords}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId1)
      expect(post.keywords.sort()).toEqual(keywords.sort())
    })

  keywords = []
  await theirClient
    .mutate({mutation: mutations.addPost, variables: {postId: postId4, imageData, keywords}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId4)
      expect(post.keywords).toEqual(keywords)
    })

  keywords = ['tea', 'here']
  await theirClient
    .mutate({mutation: mutations.addPost, variables: {postId: postId2, imageData, keywords}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId2)
      expect(post.keywords.sort()).toEqual(keywords.sort())
    })

  keywords = ['shirt', 'bug', 'bird', 'here']
  await theirClient
    .mutate({mutation: mutations.addPost, variables: {postId: postId3, imageData, keywords}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId3)
      expect(post.keywords.sort()).toEqual(keywords.sort())
    })

  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.similarPosts, variables: {postId: postId1}})
    expect(data.similarPosts.items).toHaveLength(2)
    expect(data.similarPosts.items.map((post) => post.postId).sort()).toEqual([postId1, postId3].sort())
    expect(data.similarPosts.items.map((post) => post.postedBy.userId).sort()).toEqual(
      [ourUserId, theirUserId].sort(),
    )
  })

  await ourClient
    .query({query: queries.similarPosts, variables: {postId: postId2}})
    .then(({data: {similarPosts: posts}}) => {
      expect(posts.items).toHaveLength(2)
      expect(posts.items.map((post) => post.postId).sort()).toEqual([postId2, postId3].sort())
      expect(posts.items.map((post) => post.postedBy.userId).sort()).toEqual([theirUserId, theirUserId])
    })

  await expect(ourClient.query({query: queries.similarPosts, variables: {postId: postId4}})).rejects.toThrow(
    /ClientError: Empty keywords are not allowed/,
  )
})

test('Similar posts - sort by trending score and keyword matches', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: other1Client} = await loginCache.getCleanLogin()
  const {client: other2Client} = await loginCache.getCleanLogin()

  // verify trending indexes start empty
  await ourClient.query({query: queries.allTrending}).then(({data: {trendingPosts, trendingUsers}}) => {
    expect(trendingPosts.items).toHaveLength(0)
    expect(trendingUsers.items).toHaveLength(0)
  })

  // we add three posts, with sleeps so we have determinant trending order
  const [postId1, postId2, postId3] = [uuidv4(), uuidv4(), uuidv4()]
  let keywords = ['mine', 'bird']
  await ourClient
    .mutate({
      mutation: mutations.addPost,
      variables: {postId: postId1, postType: 'TEXT_ONLY', text: 'first!', keywords},
    })
    .then(({data: {addPost: post}}) => expect(post.postStatus).toBe('COMPLETED'))
  await sleep('gsi')

  keywords = ['tea', 'here']
  await ourClient
    .mutate({
      mutation: mutations.addPost,
      variables: {postId: postId2, postType: 'TEXT_ONLY', text: '2nd!', keywords},
    })
    .then(({data: {addPost: post}}) => expect(post.postStatus).toBe('COMPLETED'))
  await sleep('gsi')

  keywords = ['shirt', 'bug', 'bird', 'here']
  await ourClient
    .mutate({
      mutation: mutations.addPost,
      variables: {postId: postId3, postType: 'TEXT_ONLY', text: '3rd!', keywords},
    })
    .then(({data: {addPost: post}}) => expect(post.postStatus).toBe('COMPLETED'))

  // other1 & other2 view the second post
  await other1Client.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId2]}})
  await other2Client.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId2]}})

  // verify trending order
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.trendingPosts})
    expect(data.trendingPosts.items).toHaveLength(3)
    expect(data.trendingPosts.items[0].postId).toBe(postId2)
    expect(data.trendingPosts.items[1].postId).toBe(postId3)
    expect(data.trendingPosts.items[2].postId).toBe(postId1)
  })

  // postId2 should be on top
  await eventually(async () => {
    const {data} = await other1Client.query({query: queries.similarPosts, variables: {postId: postId2}})
    expect(data.similarPosts.items).toHaveLength(2)
    expect(data.similarPosts.items.map((post) => post.postId)).toEqual([postId2, postId3])
  })
})
