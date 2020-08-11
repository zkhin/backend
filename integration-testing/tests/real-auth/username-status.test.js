const dotenv = require('dotenv')
const flipPromise = require('flip-promise').default
const rp = require('request-promise-native')

const cognito = require('../../utils/cognito')
jest.retryTimes(2)

dotenv.config()

const api_key = process.env.REAL_AUTH_API_KEY
if (api_key === undefined) throw new Error('Env var REAL_AUTH_API_KEY must be defined')

const api_root = process.env.REAL_AUTH_API_ROOT
if (api_root === undefined) throw new Error('Env var REAL_AUTH_API_ROOT must be defined')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

const uri = api_root + '/username/status'
const json = true
const headers = {'x-api-key': api_key}
let resp, qs

test('Malformed requests fail', async () => {
  // No api key
  resp = await flipPromise(rp.get({uri}))
  expect(resp.statusCode).toBe(403)
  expect(JSON.parse(resp.response.body)).toEqual({message: 'Forbidden'})

  // No username query param
  resp = await flipPromise(rp.get({uri, headers}))
  expect(resp.statusCode).toBe(400)
  expect(JSON.parse(resp.response.body)).toEqual({message: 'Query parameter `username` is required'})
})

test('Invalid usernames', async () => {
  // too short
  qs = {username: 'ab'}
  resp = await rp.get({uri, headers, json, qs})
  expect(resp).toEqual({status: 'INVALID'})

  // bad char
  qs = {username: 'aaa!aaa'}
  resp = await rp.get({uri, headers, json, qs})
  expect(resp).toEqual({status: 'INVALID'})

  // bad char
  qs = {username: 'aaa-aaa'}
  resp = await rp.get({uri, headers, json, qs})
  expect(resp).toEqual({status: 'INVALID'})
})

test('Username availability', async () => {
  const {username: takenUsername} = await loginCache.getCleanLogin()

  // not available
  qs = {username: takenUsername}
  resp = await rp.get({uri, headers, json, qs})
  expect(resp).toEqual({status: 'NOT_AVAILABLE'})

  // available
  qs = {username: takenUsername + 'aa_cc'}
  resp = await rp.get({uri, headers, json, qs})
  expect(resp).toEqual({status: 'AVAILABLE'})
})
