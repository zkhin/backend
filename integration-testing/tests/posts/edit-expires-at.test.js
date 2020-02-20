/* eslint-env jest */

const moment = require('moment')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const schema = require('../../utils/schema.js')

const imageData = misc.generateRandomJpeg(8, 8)
const imageDataB64 = new Buffer.from(imageData).toString('base64')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Cant edit Post.expiresAt for post that do not exist', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const variables = {
    postId: uuidv4(),
    expiresAt: moment().add(moment.duration('P1D')).toISOString(),
  }
  await expect(ourClient.mutate({mutation: schema.editPostExpiresAt, variables})).rejects.toThrow('ClientError')
})


test('Cant edit Post.expiresAt for post that isnt ours', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // they add a post
  let variables = {postId, mediaId: uuidv4(), imageData: imageDataB64}
  let resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // we try to edit its expiresAt
  variables = {postId, expiresAt: moment().add(moment.duration('P1D')).toISOString()}
  await expect(ourClient.mutate({mutation: schema.editPostExpiresAt, variables})).rejects.toThrow('ClientError')
})


test('Cant set Post.expiresAt to datetime in the past', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // we add a post
  let variables = {postId, mediaId: uuidv4(), imageData: imageDataB64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // we try to edit its expiresAt to a date in the past
  variables = {postId, expiresAt: moment().subtract(moment.duration('PT1M')).toISOString()}
  await expect(ourClient.mutate({mutation: schema.editPostExpiresAt, variables})).rejects.toThrow('ClientError')
})


test('Cant set Post.expiresAt with datetime without timezone info', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // we add a post
  let variables = {postId, mediaId: uuidv4(), imageData: imageDataB64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // we try to edit its expiresAt to a date in the past, gql schema catches this error not our server code
  variables = {postId, expiresAt: '2019-01-01T01:01:01'}
  await expect(ourClient.mutate({mutation: schema.editPostExpiresAt, variables})).rejects.toThrow('GraphQL error')
})


test('Add and remove expiresAt from a Post', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // we add a post without an expiresAt
  let variables = {postId, mediaId: uuidv4(), imageData: imageDataB64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['expiresAt']).toBeNull()

  // we edit the post to give it an expiresAt
  const expiresAt = moment().add(moment.duration('P1D'))
  variables = {postId, expiresAt: expiresAt.toISOString()}
  resp = await ourClient.mutate({mutation: schema.editPostExpiresAt, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPostExpiresAt']['postId']).toBe(postId)
  expect(resp['data']['editPostExpiresAt']['expiresAt']).not.toBeNull()
  expect(moment(resp['data']['editPostExpiresAt']['expiresAt']).isSame(expiresAt)).toBe(true)

  // we edit the post to remove its expiresAt using null
  variables = {postId, expiresAt: null}
  resp = await ourClient.mutate({mutation: schema.editPostExpiresAt, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPostExpiresAt']['postId']).toBe(postId)
  expect(resp['data']['editPostExpiresAt']['expiresAt']).toBeNull()

  // we edit the post again to give it an expiresAt
  variables = {postId, expiresAt: expiresAt.toISOString()}
  resp = await ourClient.mutate({mutation: schema.editPostExpiresAt, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPostExpiresAt']['postId']).toBe(postId)
  expect(resp['data']['editPostExpiresAt']['expiresAt']).not.toBeNull()
  expect(moment(resp['data']['editPostExpiresAt']['expiresAt']).isSame(expiresAt)).toBe(true)

  // we edit the post to remove its expiresAt using undefined
  variables = {postId}
  resp = await ourClient.mutate({mutation: schema.editPostExpiresAt, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPostExpiresAt']['postId']).toBe(postId)
  expect(resp['data']['editPostExpiresAt']['expiresAt']).toBeNull()
})


test('Edit Post.expiresAt with UTC', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()
  const lifetime = 'P1D'

  // add a post with a lifetime
  let variables = {postId, mediaId: uuidv4(), imageData: imageDataB64, lifetime}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  let post = resp['data']['addPost']
  expect(post['postId']).toBe(postId)
  expect(post['expiresAt']).not.toBeNull()
  const at = moment(post['expiresAt'])

  // change the expiresAt
  at.add(moment.duration(lifetime))
  const expiresAt = at.toISOString()
  resp = await ourClient.mutate({mutation: schema.editPostExpiresAt, variables: {postId, expiresAt}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['editPostExpiresAt']
  expect(post['postId']).toBe(postId)
  expect(post['expiresAt']).not.toBeNull()
  expect(moment(post['expiresAt']).isSame(at)).toBe(true)

  // pull the post again to make sure that new value stuck in DB
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['post']
  expect(post['postId']).toBe(postId)
  expect(post['expiresAt']).not.toBeNull()
  expect(moment(post['expiresAt']).isSame(at)).toBe(true)
})


test('Edit Post.expiresAt with non-UTC', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()
  const lifetime = 'P1D'

  // add a post with a lifetime
  let variables = {postId, mediaId: uuidv4(), imageData: imageDataB64, lifetime}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  let post = resp['data']['addPost']
  expect(post['postId']).toBe(postId)
  expect(post['expiresAt']).not.toBeNull()
  const at = moment(post['expiresAt'])

  // change the expiresAt
  at.add(moment.duration(lifetime))
  let expiresAt = at.toISOString().replace('Z', '+01:30')
  at.subtract(moment.duration('PT1H30M')) // account for the timezone offset

  resp = await ourClient.mutate({mutation: schema.editPostExpiresAt, variables: {postId, expiresAt}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['editPostExpiresAt']
  expect(post['postId']).toBe(postId)
  expect(post['expiresAt']).not.toBeNull()
  expect(moment(post['expiresAt']).isSame(at)).toBe(true)

  // pull the post again to make sure that new value stuck in DB
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['post']
  expect(post['postId']).toBe(postId)
  expect(post['expiresAt']).not.toBeNull()
  expect(moment(post['expiresAt']).isSame(at)).toBe(true)
})


test('Adding and clearing Post.expiresAt removes and adds it to users stories', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // add a post with no lifetime
  let variables = {postId, mediaId: uuidv4(), imageData: imageDataB64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['expiresAt']).toBeNull()

  // check we start with no stories
  resp = await ourClient.query({query: schema.userStories, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']['items']).toHaveLength(0)

  // set the post's expiresAt, changing it to a story
  const expiresAt = moment().add(moment.duration('PT1H')).toISOString()
  resp = await ourClient.mutate({mutation: schema.editPostExpiresAt, variables: {postId, expiresAt}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPostExpiresAt']['postId']).toBe(postId)
  expect(resp['data']['editPostExpiresAt']['expiresAt']).not.toBeNull()

  // check we now have a story
  resp = await ourClient.query({query: schema.userStories, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']['items']).toHaveLength(1)
  expect(resp['data']['user']['stories']['items'][0]['postId']).toBe(postId)

  // remove the post's expiresAt, changing it to not be a story
  resp = await ourClient.mutate({mutation: schema.editPostExpiresAt, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPostExpiresAt']['postId']).toBe(postId)
  expect(resp['data']['editPostExpiresAt']['expiresAt']).toBeNull()

  // check no longer have a story
  resp = await ourClient.query({query: schema.userStories, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']['items']).toHaveLength(0)
})


test('Clearing Post.expiresAt removes from first followed stories', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // we follow them
  let resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')

  // they add a post that is also a story
  let variables = {postId, mediaId: uuidv4(), imageData: imageDataB64, lifetime: 'PT1H'}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['expiresAt']).not.toBeNull()

  // check we see them in our first followed stories
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followedUsersWithStories']['items']).toHaveLength(1)
  expect(resp['data']['self']['followedUsersWithStories']['items'][0]['userId']).toBe(theirUserId)

  // they edit that post so it is no longer a story
  variables = {postId, expiresAt: null}
  resp = await theirClient.mutate({mutation: schema.editPostExpiresAt, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPostExpiresAt']['postId']).toBe(postId)
  expect(resp['data']['editPostExpiresAt']['expiresAt']).toBeNull()

  // check that is reflected in our first followed stories
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followedUsersWithStories']['items']).toHaveLength(0)
})


test('Changing Post.expiresAt is reflected in first followed stories', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()
  const [otherClient, otherUserId] = await loginCache.getCleanLogin()
  const theirPostId = uuidv4()
  const otherPostId = uuidv4()

  // we follow them
  let resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')

  // we follow other
  resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: otherUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')

  // they add a post that is also a story
  let variables = {postId: theirPostId, mediaId: uuidv4(), imageData: imageDataB64, lifetime: 'PT1H'}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(theirPostId)
  expect(resp['data']['addPost']['expiresAt']).not.toBeNull()
  const at = moment(resp['data']['addPost']['expiresAt'])

  // other adds a post that is also a story
  variables = {postId: otherPostId, mediaId: uuidv4(), imageData: imageDataB64, lifetime: 'PT2H'}
  resp = await otherClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(otherPostId)
  expect(resp['data']['addPost']['expiresAt']).not.toBeNull()

  // check we see them as expected in our first followed stories
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followedUsersWithStories']['items']).toHaveLength(2)
  expect(resp['data']['self']['followedUsersWithStories']['items'][0]['userId']).toBe(theirUserId)
  expect(resp['data']['self']['followedUsersWithStories']['items'][1]['userId']).toBe(otherUserId)

  // edit their post's expiration date to a date further in the future
  at.add(moment.duration('PT2H'))
  variables = {postId: theirPostId, expiresAt: at.toISOString()}
  resp = await theirClient.mutate({mutation: schema.editPostExpiresAt, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPostExpiresAt']['postId']).toBe(theirPostId)
  expect(resp['data']['editPostExpiresAt']['expiresAt']).not.toBeNull()

  // check we see them as expected in our first followed stories (order reversed from earlier)
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followedUsersWithStories']['items']).toHaveLength(2)
  expect(resp['data']['self']['followedUsersWithStories']['items'][0]['userId']).toBe(otherUserId)
  expect(resp['data']['self']['followedUsersWithStories']['items'][1]['userId']).toBe(theirUserId)

  // edit their post's expiration date to a date closer in the future
  at.subtract(moment.duration('PT2H'))
  variables = {postId: theirPostId, expiresAt: at.toISOString()}
  resp = await theirClient.mutate({mutation: schema.editPostExpiresAt, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPostExpiresAt']['postId']).toBe(theirPostId)
  expect(resp['data']['editPostExpiresAt']['expiresAt']).not.toBeNull()

  // check we see them as expected in our first followed stories (order back to original)
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followedUsersWithStories']['items']).toHaveLength(2)
  expect(resp['data']['self']['followedUsersWithStories']['items'][0]['userId']).toBe(theirUserId)
  expect(resp['data']['self']['followedUsersWithStories']['items'][1]['userId']).toBe(otherUserId)
})
