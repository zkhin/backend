import fs from 'fs'
import {v4 as uuidv4} from 'uuid'

import {cognito, eventually, fixturePath, shortRandomString} from '../../utils'
import {mutations, queries} from '../../schema'

const grantData = fs.readFileSync(fixturePath('grant.jpg'))
const grantDataB64 = new Buffer.from(grantData).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

describe('Basic searches', () => {
  let ourClient, ourUserId, ourUsername
  let theirClient

  beforeAll(async () => {
    ;({client: ourClient, userId: ourUserId, username: ourUsername} = await loginCache.getCleanLogin())
    ;({client: theirClient} = await loginCache.getCleanLogin())
  })

  test('Exact match search on username', async () => {
    await eventually(async () => {
      const {data} = await theirClient.query({query: queries.searchUsers, variables: {searchToken: ourUsername}})
      expect(data.searchUsers.items).toHaveLength(1)
      expect(data.searchUsers.items[0].userId).toBe(ourUserId)
    })
  })

  test('Prefix match on username', async () => {
    await eventually(async () => {
      const searchToken = ourUsername.slice(0, ourUsername.length / 2)
      const {data} = await theirClient.query({query: queries.searchUsers, variables: {searchToken}})
      expect(data.searchUsers.items).toHaveLength(1)
      expect(data.searchUsers.items[0].userId).toBe(ourUserId)
    })
  })

  test('Check we dont see ourselves in our search results', async () => {
    const {data} = await ourClient.query({query: queries.searchUsers, variables: {searchToken: ourUsername}})
    expect(data.searchUsers.items).toHaveLength(0)
  })
})

test('Exact match search on fullName', async () => {
  const {client, userId} = await loginCache.getCleanLogin()
  const {client: otherClient} = await loginCache.getCleanLogin()

  // change our fullName to something random and hopefully unique
  const fullName = 'FIRST' + shortRandomString() + ' LAST' + shortRandomString()
  await client.mutate({mutation: mutations.setUserDetails, variables: {fullName: fullName}})

  // give the search index a good chunk of time to update
  await eventually(async () => {
    const {data} = await otherClient.query({query: queries.searchUsers, variables: {searchToken: fullName}})
    expect(data.searchUsers.items).toHaveLength(1)
    expect(data.searchUsers.items[0].userId).toBe(userId)
  })
})

test('Search works on fullName, case insensitive', async () => {
  const {client, userId} = await loginCache.getCleanLogin()
  const {client: otherClient} = await loginCache.getCleanLogin()

  // change our fullName to something random and hopefully unique
  const fullName = 'FIRST' + shortRandomString() + ' LAST' + shortRandomString()
  await client.mutate({mutation: mutations.setUserDetails, variables: {fullName: fullName}})

  // give the search index a good chunk of time to update
  await eventually(async () => {
    const searchToken = fullName.toUpperCase()
    const {data} = await otherClient.query({query: queries.searchUsers, variables: {searchToken}})
    expect(data.searchUsers.items).toHaveLength(1)
    expect(data.searchUsers.items[0].userId).toBe(userId)
  })

  // search in all lower case, we should show up in the results
  await eventually(async () => {
    const searchToken = fullName.toLowerCase()
    const {data} = await otherClient.query({query: queries.searchUsers, variables: {searchToken}})
    expect(data.searchUsers.items).toHaveLength(1)
    expect(data.searchUsers.items[0].userId).toBe(userId)
  })
})

test('Search works on fullName, searching one name at a time', async () => {
  const {client, userId} = await loginCache.getCleanLogin()
  const {client: otherClient} = await loginCache.getCleanLogin()

  // change our fullName to something random and hopefully unique
  const firstName = 'First' + shortRandomString()
  const lastName = 'Last' + shortRandomString()
  const fullName = `${firstName} ${lastName}`
  await client.mutate({mutation: mutations.setUserDetails, variables: {fullName: fullName}})

  // search with first name
  await eventually(async () => {
    const {data} = await otherClient.query({query: queries.searchUsers, variables: {searchToken: firstName}})
    expect(data.searchUsers.items).toHaveLength(1)
    expect(data.searchUsers.items[0].userId).toBe(userId)
  })

  // search with last name
  await eventually(async () => {
    const {data} = await otherClient.query({query: queries.searchUsers, variables: {searchToken: lastName}})
    expect(data.searchUsers.items).toHaveLength(1)
    expect(data.searchUsers.items[0].userId).toBe(userId)
  })
})

test('Search works on fullName, omitting middle name', async () => {
  const {client, userId} = await loginCache.getCleanLogin()
  const {client: otherClient} = await loginCache.getCleanLogin()

  // change our fullName to something random and hopefully unique
  const firstName = 'First' + shortRandomString()
  const middleName = 'Middle' + shortRandomString()
  const lastName = 'Last' + shortRandomString()
  const fullName = `${firstName} ${middleName} ${lastName}`
  await client.mutate({mutation: mutations.setUserDetails, variables: {fullName: fullName}})

  await eventually(async () => {
    const searchToken = `${firstName} ${lastName}`
    const {data} = await otherClient.query({query: queries.searchUsers, variables: {searchToken}})
    expect(data.searchUsers.items).toHaveLength(1)
    expect(data.searchUsers.items[0].userId).toBe(userId)
  })
})

test('Search works on fullName with prefix of name', async () => {
  const {client, userId} = await loginCache.getCleanLogin()
  const {client: otherClient} = await loginCache.getCleanLogin()

  // change our fullName to something random and hopefully unique
  const firstName = 'First' + shortRandomString()
  const middleName = 'Middle' + shortRandomString()
  const lastName = 'Last' + shortRandomString()
  const fullName = `${firstName} ${middleName} ${lastName}`
  await client.mutate({mutation: mutations.setUserDetails, variables: {fullName: fullName}})

  // search with prefix of first name
  await eventually(async () => {
    const searchToken = firstName.substring(0, 8)
    const {data} = await otherClient.query({query: queries.searchUsers, variables: {searchToken}})
    expect(data.searchUsers.items).toHaveLength(1)
    expect(data.searchUsers.items[0].userId).toBe(userId)
  })

  // search with preifx of last name
  await eventually(async () => {
    const searchToken = lastName.substring(0, 8)
    const {data} = await otherClient.query({query: queries.searchUsers, variables: {searchToken}})
    expect(data.searchUsers.items).toHaveLength(1)
    expect(data.searchUsers.items[0].userId).toBe(userId)
  })
})

test('Cant do blank searches', async () => {
  const {client} = await loginCache.getCleanLogin()

  await client
    .query({query: queries.searchUsers, variables: {searchToken: null}, errorPolicy: 'all'})
    .then(({data, errors}) => {
      expect(errors.length).toBeTruthy()
      expect(data).toBeNull()
    })

  await client
    .query({query: queries.searchUsers, variables: {searchToken: ''}, errorPolicy: 'all'})
    .then(({data, errors}) => {
      expect(errors.length).toBeTruthy()
      expect(data).toBeNull()
    })

  await client
    .query({query: queries.searchUsers, variables: {searchToken: ' '}, errorPolicy: 'all'})
    .then(({data, errors}) => {
      expect(errors.length).toBeTruthy()
      expect(data).toBeNull()
    })

  await client
    .query({query: queries.searchUsers, variables: {searchToken: '   '}, errorPolicy: 'all'})
    .then(({data, errors}) => {
      expect(errors.length).toBeTruthy()
      expect(data).toBeNull()
    })

  await client
    .query({query: queries.searchUsers, variables: {searchToken: '\n'}, errorPolicy: 'all'})
    .then(({data, errors}) => {
      expect(errors.length).toBeTruthy()
      expect(data).toBeNull()
    })
})

test('Doesnt crash on special characters', async () => {
  const {client} = await loginCache.getCleanLogin()

  let resp = await client.query({query: queries.searchUsers, variables: {searchToken: '+'}})
  expect(resp.data.searchUsers.items).toHaveLength(0)

  resp = await client.query({query: queries.searchUsers, variables: {searchToken: '*'}})
  expect(resp.data.searchUsers.items).toHaveLength(0)

  resp = await client.query({query: queries.searchUsers, variables: {searchToken: '/'}})
  expect(resp.data.searchUsers.items).toHaveLength(0)

  resp = await client.query({query: queries.searchUsers, variables: {searchToken: '\\'}})
  expect(resp.data.searchUsers.items).toHaveLength(0)

  resp = await client.query({query: queries.searchUsers, variables: {searchToken: '"'}})
  expect(resp.data.searchUsers.items).toHaveLength(0)

  resp = await client.query({query: queries.searchUsers, variables: {searchToken: '?'}})
  expect(resp.data.searchUsers.items).toHaveLength(0)
})

test('Special characters do not work as wildcards', async () => {
  const {client, userId} = await loginCache.getCleanLogin()
  const {client: otherClient} = await loginCache.getCleanLogin()

  // change our username to something random and hopefully unique
  const newUsername = 'TESTER' + shortRandomString()
  await client.mutate({mutation: mutations.setUsername, variables: {username: newUsername}})

  // verify we can see that user in search results
  await eventually(async () => {
    const {data} = await otherClient.query({query: queries.searchUsers, variables: {searchToken: newUsername}})
    expect(data.searchUsers.items).toHaveLength(1)
    expect(data.searchUsers.items[0].userId).toBe(userId)
  })

  await otherClient
    .query({query: queries.searchUsers, variables: {searchToken: '-'}})
    .then(({data: {searchUsers}}) => {
      expect(searchUsers.items).toHaveLength(0)
    })

  await otherClient
    .query({query: queries.searchUsers, variables: {searchToken: '_'}})
    .then(({data: {searchUsers}}) => {
      expect(searchUsers.items).toHaveLength(0)
    })

  await otherClient
    .query({query: queries.searchUsers, variables: {searchToken: '.'}})
    .then(({data: {searchUsers}}) => {
      expect(searchUsers.items).toHaveLength(0)
    })

  await otherClient
    .query({query: queries.searchUsers, variables: {searchToken: "'"}})
    .then(({data: {searchUsers}}) => {
      expect(searchUsers.items).toHaveLength(0)
    })
})

test('User search returns urls for profile pics', async () => {
  const {client, userId} = await loginCache.getCleanLogin()
  const {client: otherClient} = await loginCache.getCleanLogin()

  // change our username to something random and hopefully unique
  const newUsername = 'TESTER' + shortRandomString()
  await client.mutate({mutation: mutations.setUsername, variables: {username: newUsername}})

  // do a search, and check that we do *not* see a photo
  await eventually(async () => {
    const {data} = await otherClient.query({query: queries.searchUsers, variables: {searchToken: newUsername}})
    expect(data.searchUsers.items).toHaveLength(1)
    expect(data.searchUsers.items[0].userId).toBe(userId)
    expect(data.searchUsers.items[0].photo).toBeNull()
  })

  // add an image post, upload that image
  const postId = uuidv4()
  let variables = {postId, imageData: grantDataB64, takenInReal: true}
  let resp = await client.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // set our profile photo to that image
  resp = await client.mutate({mutation: mutations.setUserDetails, variables: {photoPostId: postId}})
  expect(resp.data.setUserDetails.photo.url).toBeTruthy()

  // do a search, and check that we see a photo
  await eventually(async () => {
    const {data} = await otherClient.query({query: queries.searchUsers, variables: {searchToken: newUsername}})
    expect(data.searchUsers.items).toHaveLength(1)
    expect(data.searchUsers.items[0].userId).toBe(userId)
    expect(data.searchUsers.items[0].photo.url).toBeTruthy()
  })
})

test('User search prioritizes exact match on username', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: o1Client, userId: o1UserId} = await loginCache.getCleanLogin()
  const {client: o2Client, userId: o2UserId} = await loginCache.getCleanLogin()
  const name = shortRandomString()

  // other1 username matches that name exactly, fullname not match
  const o1FullName = shortRandomString()
  await o1Client
    .mutate({mutation: mutations.setUserDetails, variables: {username: name, fullName: o1FullName}})
    .then(({data}) => {
      expect(data.setUserDetails.userId).toBe(o1UserId)
      expect(data.setUserDetails.username).toBe(name)
      expect(data.setUserDetails.fullName).toBe(o1FullName)
    })

  // other2 username username to have it as a prefix, and set their full name to contain it
  const o2Username = name + shortRandomString()
  const o2FullName = name + ' ' + shortRandomString()
  await o2Client
    .mutate({mutation: mutations.setUserDetails, variables: {username: o2Username, fullName: o2FullName}})
    .then(({data}) => {
      expect(data.setUserDetails.userId).toBe(o2UserId)
      expect(data.setUserDetails.username).toBe(o2Username)
      expect(data.setUserDetails.fullName).toBe(o2FullName)
    })

  // do a search with our username, check that other1 shows up as first result
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.searchUsers, variables: {searchToken: name}})
    expect(data.searchUsers.items).toHaveLength(2)
    expect(data.searchUsers.items[0].userId).toBe(o1UserId)
    expect(data.searchUsers.items[1].userId).toBe(o2UserId)
  })
})
