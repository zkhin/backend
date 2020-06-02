/* eslint-env jest */

const fs = require('fs')
const path = require('path')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const {mutations, queries} = require('../../schema')

const grantData = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg'))
const grantDataB64 = new Buffer.from(grantData).toString('base64')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Exact match search on username', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // change our username to something random and hopefully unique
  const newUsername = 'TESTER' + misc.shortRandomString()
  let resp = await ourClient.mutate({mutation: mutations.setUsername, variables: {username: newUsername}})
  expect(resp.errors).toBeUndefined()

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: newUsername}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(1)
  expect(resp.data.searchUsers.items[0].userId).toBe(ourUserId)
})

test('Prefix match on username', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // change our username to something random and hopefully unique
  const newUsernameFirstHalf = 'TESTER' + misc.shortRandomString()
  const newUsername = newUsernameFirstHalf + misc.shortRandomString() + 'yesyes'
  let resp = await ourClient.mutate({mutation: mutations.setUsername, variables: {username: newUsername}})
  expect(resp.errors).toBeUndefined()

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  // verify exact match works
  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: newUsername}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(1)
  expect(resp.data.searchUsers.items[0].userId).toBe(ourUserId)

  // verify the prefix match works
  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: newUsernameFirstHalf}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(1)
  expect(resp.data.searchUsers.items[0].userId).toBe(ourUserId)
})

test('Exact match search on fullName', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // change our fullName to something random and hopefully unique
  const fullName = 'FIRST' + misc.shortRandomString() + ' LAST' + misc.shortRandomString()
  let resp = await ourClient.mutate({mutation: mutations.setUserDetails, variables: {fullName: fullName}})
  expect(resp.errors).toBeUndefined()

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: fullName}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(1)
  expect(resp.data.searchUsers.items[0].userId).toBe(ourUserId)
})

test('Search works on fullName, case insensitive', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // change our fullName to something random and hopefully unique
  const fullName = 'FIRST' + misc.shortRandomString() + ' LAST' + misc.shortRandomString()
  let resp = await ourClient.mutate({mutation: mutations.setUserDetails, variables: {fullName: fullName}})
  expect(resp.errors).toBeUndefined()

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  // search in all upper case, we should show up in the results
  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: fullName.toUpperCase()}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(1)
  expect(resp.data.searchUsers.items[0].userId).toBe(ourUserId)

  // search in all lower case, we should show up in the results
  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: fullName.toLowerCase()}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(1)
  expect(resp.data.searchUsers.items[0].userId).toBe(ourUserId)
})

test('Search works on fullName, searching one name at a time', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // change our fullName to something random and hopefully unique
  const firstName = 'First' + misc.shortRandomString()
  const lastName = 'Last' + misc.shortRandomString()
  const fullName = `${firstName} ${lastName}`
  let resp = await ourClient.mutate({mutation: mutations.setUserDetails, variables: {fullName: fullName}})
  expect(resp.errors).toBeUndefined()

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  // search with first name
  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: firstName}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(1)
  expect(resp.data.searchUsers.items[0].userId).toBe(ourUserId)

  // search with last name
  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: lastName}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(1)
  expect(resp.data.searchUsers.items[0].userId).toBe(ourUserId)
})

test('Search works on fullName, omitting middle name', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // change our fullName to something random and hopefully unique
  const firstName = 'First' + misc.shortRandomString()
  const middleName = 'Middle' + misc.shortRandomString()
  const lastName = 'Last' + misc.shortRandomString()
  const fullName = `${firstName} ${middleName} ${lastName}`
  let resp = await ourClient.mutate({mutation: mutations.setUserDetails, variables: {fullName: fullName}})
  expect(resp.errors).toBeUndefined()

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  // search with first name + last name
  const simpleName = `${firstName} ${lastName}`
  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: simpleName}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(1)
  expect(resp.data.searchUsers.items[0].userId).toBe(ourUserId)
})

test('Search works on fullName with prefix of name', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // change our fullName to something random and hopefully unique
  const firstName = 'First' + misc.shortRandomString()
  const middleName = 'Middle' + misc.shortRandomString()
  const lastName = 'Last' + misc.shortRandomString()
  const fullName = `${firstName} ${middleName} ${lastName}`
  let resp = await ourClient.mutate({mutation: mutations.setUserDetails, variables: {fullName: fullName}})
  expect(resp.errors).toBeUndefined()

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  // search with prefix of first name
  const partOfFirstName = firstName.substring(0, 8)
  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: partOfFirstName}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(1)
  expect(resp.data.searchUsers.items[0].userId).toBe(ourUserId)

  // search with preifx of last name
  const partOfLastName = lastName.substring(0, 8)
  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: partOfLastName}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(1)
  expect(resp.data.searchUsers.items[0].userId).toBe(ourUserId)
})

test('Cant do blank searches', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  let resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: null}})
  expect(resp.errors.length).toBeTruthy()
  expect(resp.data).toBeNull()

  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: ''}})
  expect(resp.errors.length).toBeTruthy()
  expect(resp.data).toBeNull()

  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: ' '}})
  expect(resp.errors.length).toBeTruthy()
  expect(resp.data).toBeNull()

  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: '   '}})
  expect(resp.errors.length).toBeTruthy()
  expect(resp.data).toBeNull()

  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: '\n'}})
  expect(resp.errors.length).toBeTruthy()
  expect(resp.data).toBeNull()
})

test('Doesnt crash on special characters', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  let resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: '+'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(0)

  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: '*'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(0)

  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: '/'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(0)

  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: '\\'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(0)

  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: '"'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(0)

  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: '?'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(0)
})

test('Special characters do not work as wildcards', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // change our username to something random and hopefully unique
  const newUsername = 'TESTER' + misc.shortRandomString()
  let resp = await ourClient.mutate({mutation: mutations.setUsername, variables: {username: newUsername}})
  expect(resp.errors).toBeUndefined()

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  // verify we can see that user in search results
  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: newUsername}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(1)
  expect(resp.data.searchUsers.items[0].userId).toBe(ourUserId)

  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: '-'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(0)

  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: '_'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(0)

  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: '.'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(0)

  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: "'"}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(0)
})

test('User search returns urls for profile pics', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // change our username to something random and hopefully unique
  const newUsername = 'TESTER' + misc.shortRandomString()
  let resp = await ourClient.mutate({mutation: mutations.setUsername, variables: {username: newUsername}})
  expect(resp.errors).toBeUndefined()

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  // do a search, and check that we do *not* see a photo
  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: newUsername}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(1)
  expect(resp.data.searchUsers.items[0].userId).toBe(ourUserId)
  expect(resp.data.searchUsers.items[0].photo).toBeNull()

  // add an image post, upload that image
  const postId = uuidv4()
  let variables = {postId, imageData: grantDataB64, takenInReal: true}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // set our profile photo to that image
  resp = await ourClient.mutate({mutation: mutations.setUserDetails, variables: {photoPostId: postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.setUserDetails.photo.url).toBeTruthy()

  // do a search, and check that we see a photo
  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: newUsername}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.searchUsers.items).toHaveLength(1)
  expect(resp.data.searchUsers.items[0].userId).toBe(ourUserId)
  expect(resp.data.searchUsers.items[0].photo.url).toBeTruthy()
})
