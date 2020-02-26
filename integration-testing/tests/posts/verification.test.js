/* eslint-env jest */

const fs = require('fs')
const path = require('path')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const schema = require('../../utils/schema.js')

const smallGrantData = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg'))
const smallGrantDataB64 = new Buffer.from(smallGrantData).toString('base64')
const bigGrantData = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'big-grant.jpg'))

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Add media post passes verification', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add a media post, check in PENDING
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let variables = {postId, mediaId, takenInReal: true, originalFormat: 'HEIC'}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  let post = resp['data']['addPost']
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('PENDING')
  expect(post['isVerified']).toBeNull()
  expect(post['mediaObjects']).toHaveLength(1)
  expect(post['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(post['mediaObjects'][0]['mediaStatus']).toBe('AWAITING_UPLOAD')
  expect(post['mediaObjects'][0]['isVerified']).toBe(false)  // null would be more appropriate

  // upload the media
  let uploadUrl = post['imageUploadUrl']
  expect(uploadUrl).toBeTruthy()
  expect(uploadUrl.split('?')[0]).toBe(post['mediaObjects'][0]['uploadUrl'].split('?')[0])
  await misc.uploadMedia(bigGrantData, 'image/jpeg', uploadUrl)
  await misc.sleepUntilPostCompleted(ourClient, postId)

  // check the post is now verified
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['post']
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('COMPLETED')
  expect(post['isVerified']).toBe(true)
  expect(post['mediaObjects']).toHaveLength(1)
  expect(post['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(post['mediaObjects'][0]['mediaStatus']).toBe('UPLOADED')
  expect(post['mediaObjects'][0]['isVerified']).toBe(true)
})


test('Add media post fails verification', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add a media post, give s3 trigger a second to fire
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let variables = {postId, mediaId, imageData: smallGrantDataB64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  let post = resp['data']['addPost']
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('COMPLETED')
  expect(post['isVerified']).toBe(false)
  expect(post['mediaObjects']).toHaveLength(1)
  expect(post['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(post['mediaObjects'][0]['mediaStatus']).toBe('UPLOADED')
  expect(post['mediaObjects'][0]['isVerified']).toBe(false)

  // check those values stuck in DB
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['post']
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('COMPLETED')
  expect(post['isVerified']).toBe(false)
  expect(post['mediaObjects']).toHaveLength(1)
  expect(post['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(post['mediaObjects'][0]['mediaStatus']).toBe('UPLOADED')
  expect(post['mediaObjects'][0]['isVerified']).toBe(false)
})


test('Add media post verification hidden hides verification state', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add a media post with verification hidden, give s3 trigger a second to fire
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let variables = {postId, mediaId, verificationHidden: true, imageData: smallGrantDataB64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  let post = resp['data']['addPost']
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('COMPLETED')
  expect(post['verificationHidden']).toBe(true)
  expect(post['isVerified']).toBe(true)  // even though in reality it failed verification
  expect(post['mediaObjects']).toHaveLength(1)
  expect(post['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(post['mediaObjects'][0]['mediaStatus']).toBe('UPLOADED')
  expect(post['mediaObjects'][0]['isVerified']).toBe(true)  // even though in reality it failed verification

  // check those values stuck in DB
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['post']
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('COMPLETED')
  expect(post['isVerified']).toBe(true)  // even though in reality it failed verification
  expect(post['mediaObjects']).toHaveLength(1)
  expect(post['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(post['mediaObjects'][0]['mediaStatus']).toBe('UPLOADED')
  expect(post['mediaObjects'][0]['isVerified']).toBe(true)  // even though in reality it failed verification

  // change the verification hidden setting of the post
  resp = await ourClient.mutate({mutation: schema.editPost, variables: {postId, verificationHidden: false}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPost']['postId']).toBe(postId)
  expect(resp['data']['editPost']['verificationHidden']).toBe(false)

  // now the real verification status of the media should show up
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['isVerified']).toBe(false)
  expect(resp['data']['post']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['post']['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(resp['data']['post']['mediaObjects'][0]['isVerified']).toBe(false)

  // change the verification hidden setting of the post again
  resp = await ourClient.mutate({mutation: schema.editPost, variables: {postId, verificationHidden: true}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPost']['postId']).toBe(postId)
  expect(resp['data']['editPost']['verificationHidden']).toBe(true)

  // now the real verification status of the media should *not* show up
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['isVerified']).toBe(true)
  expect(resp['data']['post']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['post']['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(resp['data']['post']['mediaObjects'][0]['isVerified']).toBe(true)
})


test('Post verification hidden setting is private to post owner', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post without setting verification hidden
  const postId = uuidv4()
  let variables = {postId, mediaId: uuidv4(), imageData: smallGrantDataB64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['verificationHidden']).toBe(false)

  // verify when we look at our post we see the verification hidden setting
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['verificationHidden']).toBe(false)

  // verify when someone else looks at our post they do *not* see the verification hidden setting
  resp = await theirClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['verificationHidden']).toBeNull()

  // we set the verification hidden setting
  resp = await ourClient.mutate({mutation: schema.editPost, variables: {postId, verificationHidden: true}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPost']['postId']).toBe(postId)
  expect(resp['data']['editPost']['verificationHidden']).toBe(true)

  // verify when we look at our post we see the verification hidden setting
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['verificationHidden']).toBe(true)

  // verify when someone else looks at our post they do *not* see the verification hidden setting
  resp = await theirClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['verificationHidden']).toBeNull()
})
