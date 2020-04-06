/* eslint-env jest */

const fs = require('fs')
const path = require('path')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const schema = require('../../utils/schema.js')

const grantData = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg'))
const grantDataB64 = new Buffer.from(grantData).toString('base64')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Exact match search on username', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // change our username to something random and hopefully unique
  const newUsername = 'TESTER' + misc.shortRandomString()
  let resp = await ourClient.mutate({mutation: schema.setUsername, variables: {username: newUsername}})
  expect(resp['errors']).toBeUndefined()

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: newUsername}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(1)
  expect(resp['data']['searchUsers']['items'][0]['userId']).toBe(ourUserId)
})


test('Search works on username, white space in token is handled', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // change our username to something random and hopefully unique
  const newUsername = 'TESTER' + misc.shortRandomString() + misc.shortRandomString() + 'yesyes'
  let resp = await ourClient.mutate({mutation: schema.setUsername, variables: {username: newUsername}})
  expect(resp['errors']).toBeUndefined()

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: newUsername}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(1)
  expect(resp['data']['searchUsers']['items'][0]['userId']).toBe(ourUserId)

  // breack the search query into two words
  const index = newUsername.length / 2
  const newToken = [newUsername.substring(0, index), newUsername.substring(index)].join(' ')
  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: newToken}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(1)
  expect(resp['data']['searchUsers']['items'][0]['userId']).toBe(ourUserId)
})


test('Exact match search on fullName', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // change our fullName to something random and hopefully unique
  const fullName = 'FIRST' + misc.shortRandomString() + ' LAST' + misc.shortRandomString()
  let resp = await ourClient.mutate({mutation: schema.setUserDetails, variables: {fullName: fullName}})
  expect(resp['errors']).toBeUndefined()

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: fullName}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(1)
  expect(resp['data']['searchUsers']['items'][0]['userId']).toBe(ourUserId)
})


test('Search works on fullName, case insensitive', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // change our fullName to something random and hopefully unique
  const fullName = 'FIRST' + misc.shortRandomString() + ' LAST' + misc.shortRandomString()
  let resp = await ourClient.mutate({mutation: schema.setUserDetails, variables: {fullName: fullName}})
  expect(resp['errors']).toBeUndefined()

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  // search in all upper case, we should show up in the results
  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: fullName.toUpperCase()}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(1)
  expect(resp['data']['searchUsers']['items'][0]['userId']).toBe(ourUserId)

  // search in all lower case, we should show up in the results
  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: fullName.toLowerCase()}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(1)
  expect(resp['data']['searchUsers']['items'][0]['userId']).toBe(ourUserId)
})


test('Search works on fullName, searching one name at a time', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // change our fullName to something random and hopefully unique
  const firstName = 'First' + misc.shortRandomString()
  const lastName = 'Last' + misc.shortRandomString()
  const fullName = `${firstName} ${lastName}`
  let resp = await ourClient.mutate({mutation: schema.setUserDetails, variables: {fullName: fullName}})
  expect(resp['errors']).toBeUndefined()

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  // search with first name
  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: firstName}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(1)
  expect(resp['data']['searchUsers']['items'][0]['userId']).toBe(ourUserId)

  // search with last name
  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: lastName}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(1)
  expect(resp['data']['searchUsers']['items'][0]['userId']).toBe(ourUserId)
})


test('Search works on fullName, omitting middle name', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // change our fullName to something random and hopefully unique
  const firstName = 'First' + misc.shortRandomString()
  const middleName = 'Middle' + misc.shortRandomString()
  const lastName = 'Last' + misc.shortRandomString()
  const fullName = `${firstName} ${middleName} ${lastName}`
  let resp = await ourClient.mutate({mutation: schema.setUserDetails, variables: {fullName: fullName}})
  expect(resp['errors']).toBeUndefined()

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  // search with first name + last name
  const simpleName = `${firstName} ${lastName}`
  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: simpleName}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(1)
  expect(resp['data']['searchUsers']['items'][0]['userId']).toBe(ourUserId)
})


test('Search works on fullName with part of a name', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // change our fullName to something random and hopefully unique
  const firstName = 'First' + misc.shortRandomString()
  const middleName = 'Middle' + misc.shortRandomString()
  const lastName = 'Last' + misc.shortRandomString()
  const fullName = `${firstName} ${middleName} ${lastName}`
  let resp = await ourClient.mutate({mutation: schema.setUserDetails, variables: {fullName: fullName}})
  expect(resp['errors']).toBeUndefined()

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  // search with part of first name
  const partOfFirstName = firstName.substring(3, 8)
  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: partOfFirstName}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(1)
  expect(resp['data']['searchUsers']['items'][0]['userId']).toBe(ourUserId)

  // search with part of last name
  const partOfLastName = lastName.substring(3, 8)
  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: partOfLastName}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(1)
  expect(resp['data']['searchUsers']['items'][0]['userId']).toBe(ourUserId)
})


test('Cant do blank searches', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  let resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: null}})
  expect(resp['errors'].length).toBeTruthy()
  expect(resp['data']).toBeNull()

  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: ''}})
  expect(resp['errors'].length).toBeTruthy()
  expect(resp['data']).toBeNull()

  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: ' '}})
  expect(resp['errors'].length).toBeTruthy()
  expect(resp['data']).toBeNull()

  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: '   '}})
  expect(resp['errors'].length).toBeTruthy()
  expect(resp['data']).toBeNull()

  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: '\n'}})
  expect(resp['errors'].length).toBeTruthy()
  expect(resp['data']).toBeNull()

  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: '+'}})
  expect(resp['errors'].length).toBeTruthy()
  expect(resp['data']).toBeNull()

  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: '*'}})
  expect(resp['errors'].length).toBeTruthy()
  expect(resp['data']).toBeNull()

  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: '/'}})
  expect(resp['errors'].length).toBeTruthy()
  expect(resp['data']).toBeNull()

  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: '\\'}})
  expect(resp['errors'].length).toBeTruthy()
  expect(resp['data']).toBeNull()

  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: '"'}})
  expect(resp['errors'].length).toBeTruthy()
  expect(resp['data']).toBeNull()

  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: '?'}})
  expect(resp['errors'].length).toBeTruthy()
  expect(resp['data']).toBeNull()
})


test('Special characters do not work as wildcards', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // change our username to something random and hopefully unique
  const newUsername = 'TESTER' + misc.shortRandomString()
  let resp = await ourClient.mutate({mutation: schema.setUsername, variables: {username: newUsername}})
  expect(resp['errors']).toBeUndefined()

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  // verify we can see that user in search results
  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: newUsername}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(1)
  expect(resp['data']['searchUsers']['items'][0]['userId']).toBe(ourUserId)

  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: '-'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(0)

  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: '_'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(0)

  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: '.'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(0)

  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: "'"}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(0)
})


test('User search returns urls for profile pics', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // change our username to something random and hopefully unique
  const newUsername = 'TESTER' + misc.shortRandomString()
  let resp = await ourClient.mutate({mutation: schema.setUsername, variables: {username: newUsername}})
  expect(resp['errors']).toBeUndefined()

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  // do a search, and check that we do *not* see a photo
  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: newUsername}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(1)
  expect(resp['data']['searchUsers']['items'][0]['userId']).toBe(ourUserId)
  expect(resp['data']['searchUsers']['items'][0]['photo']).toBeNull()

  // add an image post, upload that image
  const postId = uuidv4()
  let variables = {postId, imageData: grantDataB64}
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')

  // set our profile photo to that image
  resp = await ourClient.mutate({mutation: schema.setUserDetails, variables: {photoPostId: postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['photo']['url']).toBeTruthy()

  // do a search, and check that we see a photo
  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: newUsername}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(1)
  expect(resp['data']['searchUsers']['items'][0]['userId']).toBe(ourUserId)
  expect(resp['data']['searchUsers']['items'][0]['photo']['url']).toBeTruthy()
})
