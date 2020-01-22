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


test('Get, set, privacy', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we should default to false
  let resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['viewCountsHidden']).toBe(false)

  // we change it
  resp = await ourClient.mutate({mutation: schema.setUserViewCountsHidden, variables: {value: true}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['viewCountsHidden']).toBe(true)

  // check to make sure that version stuck
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['viewCountsHidden']).toBe(true)

  // check another user can't see values
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['viewCountsHidden']).toBeNull()
})


test('Verify it really hides view counts on user and post', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables: {postId, text: 't'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // check both us can see our view counts
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postViewedByCount']).toBe(0)

  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['postViewedByCount']).toBe(0)

  // check both us can see view counts on the post, they can't see our list of viewedBy
  resp = await ourClient.query({query: schema.getPostViewedBy, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getPost']['viewedByCount']).toBe(0)
  expect(resp['data']['getPost']['viewedBy']['items']).toHaveLength(0)

  resp = await theirClient.query({query: schema.getPostViewedBy, variables: {postId}})
  expect(resp['errors']).toHaveLength(1)
  expect(resp['data']['getPost']['viewedByCount']).toBe(0)
  expect(resp['data']['getPost']['viewedBy']).toBeNull()

  // hide our view counts
  resp = await ourClient.mutate({mutation: schema.setUserViewCountsHidden, variables: {value: true}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['viewCountsHidden']).toBe(true)

  // check niether of us can see our view counts
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postViewedByCount']).toBeNull()

  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['postViewedByCount']).toBeNull()

  // check neither of us can see view counts on the post, or the viewedBy list
  resp = await ourClient.query({query: schema.getPostViewedBy, variables: {postId}})
  expect(resp['errors']).toHaveLength(1)
  expect(resp['data']['getPost']['viewedByCount']).toBeNull()
  expect(resp['data']['getPost']['viewedBy']).toBeNull()

  resp = await theirClient.query({query: schema.getPostViewedBy, variables: {postId}})
  expect(resp['errors']).toHaveLength(1)
  expect(resp['data']['getPost']['viewedByCount']).toBeNull()
  expect(resp['data']['getPost']['viewedBy']).toBeNull()

  // unhide our view counts
  resp = await ourClient.mutate({mutation: schema.setUserViewCountsHidden, variables: {value: false}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['viewCountsHidden']).toBe(false)

  // check both us can see our view counts
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['postViewedByCount']).toBe(0)

  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['postViewedByCount']).toBe(0)

  // check both us can see view counts on it, only us the viewedBy list
  resp = await ourClient.query({query: schema.getPostViewedBy, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getPost']['viewedByCount']).toBe(0)
  expect(resp['data']['getPost']['viewedBy']['items']).toHaveLength(0)

  resp = await theirClient.query({query: schema.getPostViewedBy, variables: {postId}})
  expect(resp['errors']).toHaveLength(1)
  expect(resp['data']['getPost']['viewedByCount']).toBe(0)
  expect(resp['data']['getPost']['viewedBy']).toBeNull()
})
