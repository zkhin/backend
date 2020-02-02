/* eslint-env jest */

const fs = require('fs')
const path = require('path')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const schema = require('../../utils/schema.js')

const contentType = 'image/jpeg'
const smallGrantData = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg'))
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

  // we add a media post, give s3 trigger a second to fire
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({
    mutation: schema.addOneMediaPost,
    variables: {postId, mediaId, mediaType: 'IMAGE', takenInReal: true, originalFormat: 'HEIC'},
  })
  expect(resp['errors']).toBeUndefined()
  let post = resp['data']['addPost']
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('PENDING')
  expect(post['mediaObjects']).toHaveLength(1)
  expect(post['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(post['mediaObjects'][0]['mediaStatus']).toBe('AWAITING_UPLOAD')
  expect(post['mediaObjects'][0]['isVerified']).toBe(false)  // verification has not yet taken place
  expect(post['mediaObjects'][0]['uploadUrl']).toBeTruthy()
  expect(post['mediaObjects'][0]['url']).toBeNull()
  const uploadUrl = post['mediaObjects'][0]['uploadUrl']

  // upload the media, give S3 trigger a second to fire
  await misc.uploadMedia(bigGrantData, contentType, uploadUrl)
  await misc.sleepUntilPostCompleted(ourClient, postId)

  // check the post & media have changed status and look good
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['post']
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('COMPLETED')
  expect(post['mediaObjects']).toHaveLength(1)
  expect(post['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(post['mediaObjects'][0]['mediaStatus']).toBe('UPLOADED')
  expect(post['mediaObjects'][0]['isVerified']).toBe(true)
  expect(post['mediaObjects'][0]['uploadUrl']).toBeNull()
  expect(post['mediaObjects'][0]['url']).toBeTruthy()
})


test('Add media post fails verification', async () => {
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
  expect(post['mediaObjects'][0]['isVerified']).toBe(false)
  expect(post['mediaObjects'][0]['uploadUrl']).toBeTruthy()
  expect(post['mediaObjects'][0]['url']).toBeNull()
  const uploadUrl = post['mediaObjects'][0]['uploadUrl']

  // upload the media, give S3 trigger a second to fire
  await misc.uploadMedia(smallGrantData, contentType, uploadUrl)
  await misc.sleepUntilPostCompleted(ourClient, postId)

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


test('Add media post verification hidden hides verification state', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add a media post with verification hidden, give s3 trigger a second to fire
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({
    mutation: schema.addOneMediaPost,
    variables: {postId, mediaId, mediaType: 'IMAGE', verificationHidden: true},
  })
  expect(resp['errors']).toBeUndefined()
  let post = resp['data']['addPost']
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('PENDING')
  expect(post['verificationHidden']).toBe(true)
  expect(post['mediaObjects']).toHaveLength(1)
  expect(post['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(post['mediaObjects'][0]['mediaStatus']).toBe('AWAITING_UPLOAD')
  expect(post['mediaObjects'][0]['isVerified']).toBe(true)  // though in reality it hasn't been verified yet
  expect(post['mediaObjects'][0]['uploadUrl']).toBeTruthy()
  expect(post['mediaObjects'][0]['url']).toBeNull()
  const uploadUrl = post['mediaObjects'][0]['uploadUrl']

  // upload the media, give S3 trigger a second to fire
  await misc.uploadMedia(smallGrantData, contentType, uploadUrl)
  await misc.sleepUntilPostCompleted(ourClient, postId)

  // check the post & media have changed status and look good
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['post']
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('COMPLETED')
  expect(post['mediaObjects']).toHaveLength(1)
  expect(post['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(post['mediaObjects'][0]['mediaStatus']).toBe('UPLOADED')
  expect(post['mediaObjects'][0]['isVerified']).toBe(true)  // even though in reality it failed verification
  expect(post['mediaObjects'][0]['uploadUrl']).toBeNull()
  expect(post['mediaObjects'][0]['url']).toBeTruthy()

  // change the verification hidden setting of the post
  resp = await ourClient.mutate({mutation: schema.editPost, variables: {postId, verificationHidden: false}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPost']['postId']).toBe(postId)
  expect(resp['data']['editPost']['verificationHidden']).toBe(false)

  // now the real verification status of the media should show up
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
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
  expect(resp['data']['post']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['post']['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(resp['data']['post']['mediaObjects'][0]['isVerified']).toBe(true)
})


test('Post verification hidden setting is private to post owner', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post without setting verification hidden
  const postId = uuidv4()
  let resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables: {postId, text: 'lore ipsum'}})
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
