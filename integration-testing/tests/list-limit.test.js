/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../utils/cognito.js')
const misc = require('../utils/misc.js')
const { mutations, queries } = require('../schema')

const imageBytes = misc.generateRandomJpeg(8, 8)
const imageData = new Buffer.from(imageBytes).toString('base64')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


// Use of selfFeed is arbitrary, could use any paginated list query
test('Paginated list limits', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // verify requesting limit of -1, 0, 101 are errors
  let resp = await ourClient.query({query: queries.selfFeed, variables: {limit: -1}})
  expect(resp.errors).toHaveLength(1)
  expect(resp.data.self.feed).toBeNull()

  resp = await ourClient.query({query: queries.selfFeed, variables: {limit: 0}})
  expect(resp.errors).toHaveLength(1)
  expect(resp.data.self.feed).toBeNull()

  resp = await ourClient.query({query: queries.selfFeed, variables: {limit: 101}})
  expect(resp.errors).toHaveLength(1)
  expect(resp.data.self.feed).toBeNull()

  // verify requesting limit of 1, 100 are ok
  resp = await ourClient.query({query: queries.selfFeed, variables: {limit: 1}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.feed.items).toHaveLength(0)
  resp = await ourClient.query({query: queries.selfFeed, variables: {limit: 100}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.feed.items).toHaveLength(0)
})


// Use of comments is arbitrary, could use any paginated list query
test('Paginated list default', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // add a post
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)

  // add 21 comments to the post
  let commentId
  for (let i=0; i < 21; i++) {
    commentId = uuidv4()
    resp = await ourClient.mutate({mutation: mutations.addComment, variables: {postId, commentId, text: 't'}})
    expect(resp.errors).toBeUndefined()
  }

  // verify not specifying a limit results in a default of 20
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.comments.items).toHaveLength(20)
})
