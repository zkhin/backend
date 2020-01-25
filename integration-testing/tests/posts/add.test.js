/* eslint-env jest */

const moment = require('moment')
const path = require('path')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const schema = require('../../utils/schema.js')

const contentType = 'image/jpeg'
const filePath = path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Add text-only post no expiration', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  const postId = uuidv4()
  const text = 'zeds dead baby, zeds dead'
  let resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables: {postId, text}})
  expect(resp['errors']).toBeUndefined()
  let post = resp['data']['addPost']
  expect(post['postId']).toBe(postId)
  expect(post['text']).toBe(text)
  expect(post['expiresAt']).toBeNull()

  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['post']
  expect(post['postId']).toBe(postId)
  expect(post['text']).toBe(text)
  expect(post['expiresAt']).toBeNull()

  resp = await ourClient.query({query: schema.getPosts})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getPosts']['items']).toHaveLength(1)
  post = resp['data']['getPosts']['items'][0]
  expect(post['postId']).toBe(postId)
  expect(post['postedBy']['userId']).toBe(ourUserId)
  expect(post['text']).toBe(text)
  expect(post['expiresAt']).toBeNull()

  resp = await ourClient.query({query: schema.getFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getFeed']['items']).toHaveLength(1)
  expect(resp['data']['getFeed']['items'][0]['postId']).toEqual(postId)
})


test('Add text-only post with expiration', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  const postId = uuidv4()
  const text = 'zeds dead baby, zeds dead'
  const lifetime = 'P7D'
  let resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables: {postId, text, lifetime}})
  expect(resp['errors']).toBeUndefined()
  const post = resp['data']['addPost']
  expect(post['postId']).toBe(postId)
  expect(post['text']).toBe(text)
  expect(post['postedAt']).not.toBeNull()
  expect(post['expiresAt']).not.toBeNull()
  const expected_expires_at = moment(post['postedAt'])
  expected_expires_at.add(moment.duration(lifetime))
  const expires_at = moment(post['expiresAt'])
  expect(expires_at.isSame(expected_expires_at)).toBe(true)
})


test('Add media post', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add a media post, give s3 trigger a second to fire
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({
    mutation: schema.addOneMediaPost,
    variables: {postId, mediaId, mediaType: 'IMAGE'},
  })
  expect(resp['errors']).toBeUndefined()
  let post = resp['data']['addPost']
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('PENDING')
  expect(post['mediaObjects']).toHaveLength(1)
  expect(post['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(post['mediaObjects'][0]['mediaStatus']).toBe('AWAITING_UPLOAD')
  expect(post['mediaObjects'][0]['uploadUrl']).toBeTruthy()
  expect(post['mediaObjects'][0]['url']).toBeNull()
  const uploadUrl = post['mediaObjects'][0]['uploadUrl']

  // upload the media, give S3 trigger a second to fire
  await misc.uploadMedia(filePath, contentType, uploadUrl)
  await misc.sleep(3000)

  // check the post & media have changed status and look good
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['post']
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('COMPLETED')
  expect(post['mediaObjects']).toHaveLength(1)
  expect(post['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(post['mediaObjects'][0]['mediaStatus']).toBe('UPLOADED')
  expect(post['mediaObjects'][0]['isVerified']).toBe(false)
  expect(post['mediaObjects'][0]['uploadUrl']).toBeNull()
  expect(post['mediaObjects'][0]['url']).toBeTruthy()
})


test('Cannot add text-only post with invalid lifetime', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()
  const text = 'lore ipsum'

  // malformed duration string
  await expect(ourClient.mutate({
    mutation: schema.addTextOnlyPost,
    variables: {postId, text, lifetime: 'invalid'},
  })).rejects.toThrow()

  // negative value for lifetime
  await expect(ourClient.mutate({
    mutation: schema.addTextOnlyPost,
    variables: {postId, text, lifetime: '-P1D'},
  })).rejects.toThrow()

  // zero value for lifetime
  await expect(ourClient.mutate({
    mutation: schema.addTextOnlyPost,
    variables: {postId, text, lifetime: 'P0D'},
  })).rejects.toThrow()
})


test('Mental health settings default values', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // no user-level settings set
  let variables = {postId: uuidv4(), text: 'lore ipsum'}
  let resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(variables.postId)
  expect(resp['data']['addPost']['commentsDisabled']).toBe(false)
  expect(resp['data']['addPost']['likesDisabled']).toBe(false)
  expect(resp['data']['addPost']['verificationHidden']).toBe(false)

  // set user-level mental health settings to true (which provide the defaults)
  variables = {commentsDisabled: true, likesDisabled: true, verificationHidden: true}
  resp = await ourClient.mutate({mutation: schema.setUserMentalHealthSettings, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['userId']).toBe(ourUserId)
  expect(resp['data']['setUserDetails']['commentsDisabled']).toBe(true)
  expect(resp['data']['setUserDetails']['likesDisabled']).toBe(true)
  expect(resp['data']['setUserDetails']['verificationHidden']).toBe(true)

  // check those new user-level settings are used as defaults for a new post
  variables = {postId: uuidv4(), text: 'lore ipsum'}
  resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(variables.postId)
  expect(resp['data']['addPost']['commentsDisabled']).toBe(true)
  expect(resp['data']['addPost']['likesDisabled']).toBe(true)
  expect(resp['data']['addPost']['verificationHidden']).toBe(true)

  // change the user-level mental health setting defaults
  variables = {commentsDisabled: false, likesDisabled: false, verificationHidden: false}
  resp = await ourClient.mutate({mutation: schema.setUserMentalHealthSettings, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['userId']).toBe(ourUserId)
  expect(resp['data']['setUserDetails']['commentsDisabled']).toBe(false)
  expect(resp['data']['setUserDetails']['likesDisabled']).toBe(false)
  expect(resp['data']['setUserDetails']['verificationHidden']).toBe(false)

  // check those new user-level settings are used as defaults for a new post
  variables = {postId: uuidv4(), text: 'lore ipsum'}
  resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(variables.postId)
  expect(resp['data']['addPost']['commentsDisabled']).toBe(false)
  expect(resp['data']['addPost']['likesDisabled']).toBe(false)
  expect(resp['data']['addPost']['verificationHidden']).toBe(false)
})


test('Mental health settings specify values', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const text = 'zeds dead baby, zeds dead'

  // create a post, specify both to false
  let postId = uuidv4()
  let variables = {postId, text, commentsDisabled: false, likesDisabled: false, verificationHidden: false}
  let resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['commentsDisabled']).toBe(false)
  expect(resp['data']['addPost']['likesDisabled']).toBe(false)
  expect(resp['data']['addPost']['verificationHidden']).toBe(false)

  // double check those values stuck
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['commentsDisabled']).toBe(false)
  expect(resp['data']['post']['likesDisabled']).toBe(false)
  expect(resp['data']['post']['verificationHidden']).toBe(false)

  // create a post, specify both to true
  postId = uuidv4()
  variables = {postId, text, commentsDisabled: true, likesDisabled: true, verificationHidden: true}
  resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['commentsDisabled']).toBe(true)
  expect(resp['data']['addPost']['likesDisabled']).toBe(true)
  expect(resp['data']['addPost']['verificationHidden']).toBe(true)

  // double check those values stuck
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['commentsDisabled']).toBe(true)
  expect(resp['data']['post']['likesDisabled']).toBe(true)
  expect(resp['data']['post']['verificationHidden']).toBe(true)
})
