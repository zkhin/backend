/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const schema = require('../../utils/schema.js')

const imageBytes = misc.generateRandomJpeg(8, 8)
const imageData = new Buffer.from(imageBytes).toString('base64')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('No text tags', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // post with no text
  let variables = {postId: uuidv4(), mediaId: uuidv4()}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['text']).toBeNull()
  expect(resp['data']['addPost']['textTaggedUsers']).toHaveLength(0)

  // post with text, but no tagged users
  let text = 'zeds dead baby, zeds dead'
  variables = {postId: uuidv4(), mediaId: uuidv4(), text}
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['text']).toBe(text)
  expect(resp['data']['addPost']['textTaggedUsers']).toHaveLength(0)

  // post with text and tags, but those don't match to a user on the backend
  const username = cognito.generateUsername()
  text = `you do not exist, right @${username}?`
  variables = {postId: uuidv4(), mediaId: uuidv4(), text}
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['text']).toBe(text)
  expect(resp['data']['addPost']['textTaggedUsers']).toHaveLength(0)
})


test('Lots of text tags, current username does not match tagged one', async () => {
  const [ourClient, ourUserId, , , ourUsername] = await loginCache.getCleanLogin()
  const [, theirUserId, , , theirUsername] = await loginCache.getCleanLogin()
  const [, otherUserId, , , otherUsername] = await loginCache.getCleanLogin()

  // add a post with a few tags, including a repeat
  let postId = uuidv4()
  let text = `hi @${theirUsername}! hi from @${ourUsername} What's up @${theirUsername}? you, @${otherUsername} ??`
  let resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId: uuidv4(), text}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['text']).toBe(text)
  expect(resp['data']['addPost']['textTaggedUsers']).toHaveLength(3)

  // order is not defined on the textTaggedUsers, so sort it
  const cmp = (x, y) => x['tag'].localeCompare(y['tag'])
  let expectedTextTaggedUsers = [
    {tag: `@${theirUsername}`, user: {userId: theirUserId, username: theirUsername}},
    {tag: `@${ourUsername}`, user: {userId: ourUserId, username: ourUsername}},
    {tag: `@${otherUsername}`, user: {userId: otherUserId, username: otherUsername}},
  ].sort(cmp)
  let textTaggedUsers = resp['data']['addPost']['textTaggedUsers'].sort(cmp)
  // the response from network has some extra properties we want to ignore, doing it the obvious way
  expect(textTaggedUsers[0]['tag']).toBe(expectedTextTaggedUsers[0]['tag'])
  expect(textTaggedUsers[1]['tag']).toBe(expectedTextTaggedUsers[1]['tag'])
  expect(textTaggedUsers[2]['tag']).toBe(expectedTextTaggedUsers[2]['tag'])
  expect(textTaggedUsers[0]['user']['userId']).toBe(expectedTextTaggedUsers[0]['user']['userId'])
  expect(textTaggedUsers[1]['user']['userId']).toBe(expectedTextTaggedUsers[1]['user']['userId'])
  expect(textTaggedUsers[2]['user']['userId']).toBe(expectedTextTaggedUsers[2]['user']['userId'])
  expect(textTaggedUsers[0]['user']['username']).toBe(expectedTextTaggedUsers[0]['user']['username'])
  expect(textTaggedUsers[1]['user']['username']).toBe(expectedTextTaggedUsers[1]['user']['username'])
  expect(textTaggedUsers[2]['user']['username']).toBe(expectedTextTaggedUsers[2]['user']['username'])
})


test('Changing username should not affect who is in tags', async () => {
  const [ourClient, ourUserId, , , ourUsername] = await loginCache.getCleanLogin()

  // add a post in which we tag ourselves
  let postId = uuidv4()
  let text = `hi me @${ourUsername}!`
  let resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId: uuidv4(), text}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['text']).toBe(text)
  expect(resp['data']['addPost']['textTaggedUsers']).toHaveLength(1)
  expect(resp['data']['addPost']['textTaggedUsers'][0]['tag']).toBe(`@${ourUsername}`)
  expect(resp['data']['addPost']['textTaggedUsers'][0]['user']['userId']).toBe(ourUserId)
  expect(resp['data']['addPost']['textTaggedUsers'][0]['user']['username']).toBe(ourUsername)

  // we change our username
  const ourNewUsername = ourUsername.split('').reverse().join('')
  resp = await ourClient.mutate({mutation: schema.setUsername, variables: {username: ourNewUsername}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['username']).toBe(ourNewUsername)

  // look at the post again, text tags shouldn't have changed
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['text']).toBe(text)
  expect(resp['data']['post']['textTaggedUsers']).toHaveLength(1)
  expect(resp['data']['post']['textTaggedUsers'][0]['tag']).toBe(`@${ourUsername}`)
  expect(resp['data']['post']['textTaggedUsers'][0]['user']['userId']).toBe(ourUserId)
  expect(resp['data']['post']['textTaggedUsers'][0]['user']['username']).toBe(ourNewUsername)
})


test('Tags of usernames with special characters', async () => {
  // Allowed characters for usernames: alphanumeric, underscore and dot
  // Only testing one (dificult) case one here, unit tests will get all the corner cases
  const [ourClient, ourUserId, , , ourOldUsername] = await loginCache.getCleanLogin()
  const ourUsername = `._._${ourOldUsername}_.._`
  let resp = await ourClient.mutate({mutation: schema.setUsername, variables: {username: ourUsername}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['username']).toBe(ourUsername)

  // create a post and tag ourselves
  let postId = uuidv4()
  let text = `talking to myself @${ourUsername}-!?`
  resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId: uuidv4(), text}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['text']).toBe(text)
  expect(resp['data']['addPost']['textTaggedUsers']).toHaveLength(1)
  expect(resp['data']['addPost']['textTaggedUsers'][0]['tag']).toBe(`@${ourUsername}`)
  expect(resp['data']['addPost']['textTaggedUsers'][0]['user']['userId']).toBe(ourUserId)
  expect(resp['data']['addPost']['textTaggedUsers'][0]['user']['username']).toBe(ourUsername)
})


test('Tagged user blocks caller', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId, , , theirUsername] = await loginCache.getCleanLogin()
  const [otherClient] = await loginCache.getCleanLogin()

  // other adds a post that tags them
  let postId = uuidv4()
  let text = `hi @${theirUsername}`
  let variables = {postId, mediaId: uuidv4(), text, imageData}
  let resp = await otherClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['text']).toBe(text)
  expect(resp['data']['addPost']['textTaggedUsers']).toHaveLength(1)
  expect(resp['data']['addPost']['textTaggedUsers'][0]['tag']).toBe(`@${theirUsername}`)
  expect(resp['data']['addPost']['textTaggedUsers'][0]['user']['userId']).toBe(theirUserId)
  expect(resp['data']['addPost']['textTaggedUsers'][0]['user']['username']).toBe(theirUsername)

  // we see tags of them in the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['text']).toBe(text)
  expect(resp['data']['post']['textTaggedUsers']).toHaveLength(1)
  expect(resp['data']['post']['textTaggedUsers'][0]['tag']).toBe(`@${theirUsername}`)
  expect(resp['data']['post']['textTaggedUsers'][0]['user']['userId']).toBe(theirUserId)
  expect(resp['data']['post']['textTaggedUsers'][0]['user']['username']).toBe(theirUsername)

  // they block us
  resp = await theirClient.mutate({mutation: schema.blockUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(ourUserId)
  expect(resp['data']['blockUser']['blockedStatus']).toBe('BLOCKING')

  // we don't see the tag anymore
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['text']).toBe(text)
  expect(resp['data']['post']['textTaggedUsers']).toHaveLength(0)
})
