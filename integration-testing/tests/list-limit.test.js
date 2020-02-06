/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../utils/cognito.js')
const schema = require('../utils/schema.js')

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
  let resp = await ourClient.query({query: schema.selfFeed, variables: {limit: -1}})
  expect(resp['errors']).toHaveLength(1)
  expect(resp['data']['self']['feed']).toBeNull()

  resp = await ourClient.query({query: schema.selfFeed, variables: {limit: 0}})
  expect(resp['errors']).toHaveLength(1)
  expect(resp['data']['self']['feed']).toBeNull()

  resp = await ourClient.query({query: schema.selfFeed, variables: {limit: 101}})
  expect(resp['errors']).toHaveLength(1)
  expect(resp['data']['self']['feed']).toBeNull()

  // verify requesting limit of 1, 100 are ok
  resp = await ourClient.query({query: schema.selfFeed, variables: {limit: 1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(0)
  resp = await ourClient.query({query: schema.selfFeed, variables: {limit: 100}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(0)
})


// Use of selfFeed is arbitrary, could use any paginated list query
test('Paginated list default', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // add 21 text-only posts
  let resp, postId
  for (let i=0; i < 21; i++) {
    postId = uuidv4()
    resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables: {postId, text: 't'}})
    expect(resp['errors']).toBeUndefined()
  }

  // verify not specifying a limit results in a default of 20
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(20)
})
