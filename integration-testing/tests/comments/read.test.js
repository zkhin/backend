/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const schema = require('../../utils/schema.js')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('One user adds multiple comments, ordering', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, text: 'lore ipsum'}
  let resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['commentCount']).toBe(0)
  expect(resp['data']['addPost']['comments']['items']).toHaveLength(0)

  // we add a comment on the post
  const commentId1 = uuidv4()
  variables = {commentId: commentId1, postId, text: 'lore'}
  resp = await ourClient.mutate({mutation: schema.addComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addComment']['commentId']).toBe(commentId1)

  // we add another comment on the post
  const commentId2 = uuidv4()
  variables = {commentId: commentId2, postId, text: 'ipsum'}
  resp = await ourClient.mutate({mutation: schema.addComment, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addComment']['commentId']).toBe(commentId2)

  // check we see both comments, in order, on the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['commentCount']).toBe(2)
  expect(resp['data']['post']['comments']['items']).toHaveLength(2)
  expect(resp['data']['post']['comments']['items'][0]['commentId']).toBe(commentId1)
  expect(resp['data']['post']['comments']['items'][0]['commentedBy']['userId']).toBe(ourUserId)
  expect(resp['data']['post']['comments']['items'][1]['commentId']).toBe(commentId2)
  expect(resp['data']['post']['comments']['items'][1]['commentedBy']['userId']).toBe(ourUserId)
})
