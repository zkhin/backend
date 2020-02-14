/* eslint-env jest */

const fs = require('fs')
const path = require('path')
const requestImageSize = require('request-image-size')
const uuidv4 = require('uuid/v4')

const cognito = require('../utils/cognito.js')
const misc = require('../utils/misc.js')
const schema = require('../utils/schema.js')

const imageData = fs.readFileSync(path.join(__dirname, '..', 'fixtures', 'grant.jpg'))
const imageContentType = 'image/jpeg'
const imageHeight = 320
const imageWidth = 240

const bigImageData = fs.readFileSync(path.join(__dirname, '..', 'fixtures', 'big-blank.jpg'))
const bigImageContentType = 'image/jpeg'
const bigImageHeight = 2000
const bigImageWidth = 4000

const pngData = fs.readFileSync(path.join(__dirname, '..', 'fixtures', 'squirrel.png'))
const pngContentType = 'image/png'

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Add post with two images', async () => {
  const [appsyncClient, userId] = await loginCache.getCleanLogin()
  // a few consts, variables
  let resp, post, uploadUrl, media1, media2

  // add a pending post object with two images
  const postId = uuidv4()
  const mediaId1 = uuidv4()
  const mediaId2 = uuidv4()
  resp = await appsyncClient.mutate({mutation: schema.addTwoMediaPost, variables: {postId, mediaId1, mediaId2}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['addPost']
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('PENDING')
  expect(post['mediaObjects']).toHaveLength(2)
  if (post['mediaObjects'][0]['mediaId'] === mediaId1) [media1, media2] = post['mediaObjects']
  else [media2, media1] = post['mediaObjects']
  expect(media1['mediaId']).toBe(mediaId1)
  expect(media1['mediaStatus']).toBe('AWAITING_UPLOAD')
  expect(media1['mediaType']).toBe('IMAGE')
  expect(media1['url']).toBeNull()
  expect(media1['uploadUrl']).toMatch(/^https:\/\//)
  expect(media2['mediaId']).toBe(mediaId2)
  expect(media2['mediaStatus']).toBe('AWAITING_UPLOAD')
  expect(media2['mediaType']).toBe('IMAGE')
  expect(media2['url']).toBeNull()
  expect(media2['uploadUrl']).toMatch(/^https:\/\//)

  // upload the first of those images, give the s3 trigger a second to fire
  uploadUrl = media1['uploadUrl']
  await misc.uploadMedia(imageData, imageContentType, uploadUrl)
  await misc.sleep(5000)  // no way to check if just this one media object is done uploading

  // get the post and check that everything looks as expected
  resp = await appsyncClient.query({query: schema.userPosts, variables: {userId, postStatus: 'PENDING'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toHaveLength(1)
  post = resp['data']['user']['posts']['items'][0]
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('PENDING')
  expect(post['mediaObjects']).toHaveLength(2)
  if (post['mediaObjects'][0]['mediaId'] === mediaId1) [media1, media2] = post['mediaObjects']
  else [media2, media1] = post['mediaObjects']
  expect(media1['mediaId']).toBe(mediaId1)
  expect(media1['mediaStatus']).toBe('UPLOADED')
  expect(media1['url']).toMatch(/^https:\/\//)
  expect(media1['uploadUrl']).toBeNull()
  expect(media2['mediaId']).toBe(mediaId2)
  expect(media2['mediaStatus']).toBe('AWAITING_UPLOAD')
  expect(media2['url']).toBeNull()
  expect(media2['uploadUrl']).toMatch(/^https:\/\//)

  // we shouldn't find any completed posts now
  resp = await appsyncClient.query({query: schema.userPosts, variables: {userId, postStatus: 'COMPLETED'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toHaveLength(0)

  // upload the second of those images, give the s3 trigger a second to fire
  uploadUrl = media2['uploadUrl']
  await misc.uploadMedia(imageData, imageContentType, uploadUrl)
  await misc.sleepUntilPostCompleted(appsyncClient, postId)

  // get the post and check that everything looks as expected
  resp = await appsyncClient.query({query: schema.userPosts, variables: {userId, postStatus: 'COMPLETED'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toHaveLength(1)
  post = resp['data']['user']['posts']['items'][0]
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('COMPLETED')
  expect(post['mediaObjects']).toHaveLength(2)
  if (post['mediaObjects'][0]['mediaId'] === mediaId1) [media1, media2] = post['mediaObjects']
  else [media2, media1] = post['mediaObjects']
  expect(media1['mediaId']).toBe(mediaId1)
  expect(media1['mediaStatus']).toBe('UPLOADED')
  expect(media1['url']).toMatch(/^https:\/\//)
  expect(media1['uploadUrl']).toBeNull()
  expect(media2['mediaId']).toBe(mediaId2)
  expect(media2['mediaStatus']).toBe('UPLOADED')
  expect(media2['url']).toMatch(/^https:\/\//)
  expect(media2['uploadUrl']).toBeNull()

  // we shouldn't find any pending posts now
  resp = await appsyncClient.query({query: schema.userPosts, variables: {userId, postStatus: 'PENDING'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toHaveLength(0)
})


test('Uploading image sets width, height and colors', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: schema.addOneMediaPost, variables: {postId, mediaId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(resp['data']['addPost']['mediaObjects'][0]['height']).toBeNull()
  expect(resp['data']['addPost']['mediaObjects'][0]['width']).toBeNull()
  expect(resp['data']['addPost']['mediaObjects'][0]['colors']).toBeNull()
  const uploadUrl = resp['data']['addPost']['mediaObjects'][0]['uploadUrl']

  // double check width, height and colors are not yet set
  resp = await ourClient.query({
    query: schema.userMediaObjects,
    variables: {userId: ourUserId, mediaStatus: 'AWAITING_UPLOAD'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toHaveLength(1)
  expect(resp['data']['user']['mediaObjects']['items'][0]['mediaId']).toBe(mediaId)
  expect(resp['data']['user']['mediaObjects']['items'][0]['height']).toBeNull()
  expect(resp['data']['user']['mediaObjects']['items'][0]['width']).toBeNull()
  expect(resp['data']['user']['mediaObjects']['items'][0]['colors']).toBeNull()

  // upload the first of those images, give the s3 trigger a second to fire
  await misc.uploadMedia(imageData, imageContentType, uploadUrl)
  await misc.sleepUntilPostCompleted(ourClient, postId)

  // check width, height and colors are now set
  resp = await ourClient.query({query: schema.userMediaObjects, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toHaveLength(1)
  expect(resp['data']['user']['mediaObjects']['items'][0]['mediaId']).toBe(mediaId)
  expect(resp['data']['user']['mediaObjects']['items'][0]['height']).toBe(imageHeight)
  expect(resp['data']['user']['mediaObjects']['items'][0]['width']).toBe(imageWidth)
  expect(resp['data']['user']['mediaObjects']['items'][0]['colors']).toHaveLength(5)
  expect(resp['data']['user']['mediaObjects']['items'][0]['colors'][0]['r']).not.toBeNull()
  expect(resp['data']['user']['mediaObjects']['items'][0]['colors'][0]['g']).not.toBeNull()
  expect(resp['data']['user']['mediaObjects']['items'][0]['colors'][0]['b']).not.toBeNull()
})


test('Uploading png image results in error', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: schema.addOneMediaPost, variables: {postId, mediaId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId)
  const uploadUrl = resp['data']['addPost']['mediaObjects'][0]['uploadUrl']

  // upload a png, give the s3 trigger a second to fire
  await misc.uploadMedia(pngData, pngContentType, uploadUrl)
  await misc.sleep(5000)

  // check that media ended up in an ERROR state
  resp = await ourClient.query({
    query: schema.userMediaObjects,
    variables: {userId: ourUserId, mediaStatus: 'ERROR'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toHaveLength(1)
  expect(resp['data']['user']['mediaObjects']['items'][0]['mediaId']).toBe(mediaId)
})


test('Thumbnails built on successful upload', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: schema.addOneMediaPost, variables: {postId, mediaId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId)
  const uploadUrl = resp['data']['addPost']['mediaObjects'][0]['uploadUrl']

  // upload a big jpeg, give the s3 trigger a second to fire
  await misc.uploadMedia(bigImageData, bigImageContentType, uploadUrl)
  await misc.sleep(5000)  // big jpeg, so takes at least a few seconds to process
  await misc.sleepUntilPostCompleted(ourClient, postId)

  resp = await ourClient.query({query: schema.userMediaObjects, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toHaveLength(1)
  expect(resp['data']['user']['mediaObjects']['items'][0]['mediaId']).toBe(mediaId)
  const url = resp['data']['user']['mediaObjects']['items'][0]['url']
  const url64p = resp['data']['user']['mediaObjects']['items'][0]['url64p']
  const url480p = resp['data']['user']['mediaObjects']['items'][0]['url480p']
  const url1080p = resp['data']['user']['mediaObjects']['items'][0]['url1080p']
  const url4k = resp['data']['user']['mediaObjects']['items'][0]['url4k']
  expect(url).toBeTruthy()
  expect(url64p).toBeTruthy()
  expect(url480p).toBeTruthy()
  expect(url4k).toBeTruthy()

  // check the native image size dims
  let size = await requestImageSize(url)
  expect(size.width).toBe(bigImageWidth)
  expect(size.height).toBe(bigImageHeight)

  // check the 64p image size dims
  size = await requestImageSize(url64p)
  expect(size.width).toBe(114)
  expect(size.height).toBeLessThan(64)

  // check the 480p image size dims
  size = await requestImageSize(url480p)
  expect(size.width).toBe(854)
  expect(size.height).toBeLessThan(480)

  // check the 1080p image size dims
  size = await requestImageSize(url1080p)
  expect(size.width).toBe(1920)
  expect(size.height).toBeLessThan(1080)

  // check the 4k image size dims
  size = await requestImageSize(url4k)
  expect(size.width).toBe(3840)
  expect(size.height).toBeLessThan(2160)
})
