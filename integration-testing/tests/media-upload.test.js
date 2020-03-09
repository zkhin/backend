/* eslint-env jest */

const fs = require('fs')
const path = require('path')
const requestImageSize = require('request-image-size')
const rp = require('request-promise-native')
const uuidv4 = require('uuid/v4')

const cognito = require('../utils/cognito.js')
const misc = require('../utils/misc.js')
const schema = require('../utils/schema.js')

const jpgHeaders = {'Content-Type': 'image/jpeg'}
const pngHeaders = {'Content-Type': 'image/png'}

const imageData = fs.readFileSync(path.join(__dirname, '..', 'fixtures', 'grant.jpg'))
const imageHeight = 320
const imageWidth = 240

const bigImageData = fs.readFileSync(path.join(__dirname, '..', 'fixtures', 'big-blank.jpg'))
const bigImageHeight = 2000
const bigImageWidth = 4000

const pngData = fs.readFileSync(path.join(__dirname, '..', 'fixtures', 'squirrel.png'))

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Verify cannot add post with more than one image', async () => {
  const [client] = await loginCache.getCleanLogin()

  // add a pending post object with two images
  const postId = uuidv4()
  const variables = {postId, mediaId1: uuidv4(), mediaId2: uuidv4()}
  await expect(client.mutate({mutation: schema.addPostTwoMedia, variables})).rejects.toThrow('ClientError')

  // verify the post did not get created
  let resp = await client.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']).toBeNull()
})


test('Uploading image sets width, height and colors', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let variables = {postId, mediaId}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['image']).toBeNull()
  expect(resp['data']['addPost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(resp['data']['addPost']['mediaObjects'][0]['height']).toBeNull()
  expect(resp['data']['addPost']['mediaObjects'][0]['width']).toBeNull()
  expect(resp['data']['addPost']['mediaObjects'][0]['colors']).toBeNull()
  const uploadUrl = resp['data']['addPost']['imageUploadUrl']
  expect(uploadUrl.split('?')[0]).toBe(resp['data']['addPost']['mediaObjects'][0]['uploadUrl'].split('?')[0])

  // double check width, height and colors are not yet set
  variables = {userId: ourUserId, mediaStatus: 'AWAITING_UPLOAD'}
  resp = await ourClient.query({query: schema.userMediaObjects, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toHaveLength(1)
  expect(resp['data']['user']['mediaObjects']['items'][0]['mediaId']).toBe(mediaId)
  expect(resp['data']['user']['mediaObjects']['items'][0]['height']).toBeNull()
  expect(resp['data']['user']['mediaObjects']['items'][0]['width']).toBeNull()
  expect(resp['data']['user']['mediaObjects']['items'][0]['colors']).toBeNull()

  variables = {postId}
  resp = await ourClient.query({query: schema.post, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['image']).toBeNull()

  // upload the first of those images, give the s3 trigger a second to fire
  await rp.put({url: uploadUrl, headers: jpgHeaders, body: imageData})
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

  variables = {postId}
  resp = await ourClient.query({query: schema.post, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['image']['height']).toBe(imageHeight)
  expect(resp['data']['post']['image']['width']).toBe(imageWidth)
  expect(resp['data']['post']['image']['colors']).toHaveLength(5)
  expect(resp['data']['post']['image']['colors'][0]['r']).not.toBeNull()
  expect(resp['data']['post']['image']['colors'][0]['g']).not.toBeNull()
  expect(resp['data']['post']['image']['colors'][0]['b']).not.toBeNull()
})


test('Uploading png image results in error', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId)
  const uploadUrl = resp['data']['addPost']['imageUploadUrl']
  expect(uploadUrl.split('?')[0]).toBe(resp['data']['addPost']['mediaObjects'][0]['uploadUrl'].split('?')[0])

  // upload a png, give the s3 trigger a second to fire
  await rp.put({url: uploadUrl, headers: pngHeaders, body: pngData})
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
  let resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId)
  const uploadUrl = resp['data']['addPost']['imageUploadUrl']
  expect(uploadUrl.split('?')[0]).toBe(resp['data']['addPost']['mediaObjects'][0]['uploadUrl'].split('?')[0])

  // upload a big jpeg, give the s3 trigger a second to fire
  await rp.put({url: uploadUrl, headers: jpgHeaders, body: bigImageData})
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
  expect(url1080p).toBeTruthy()
  expect(url4k).toBeTruthy()

  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  const image = resp['data']['post']['image']
  expect(image).toBeTruthy()

  // check the native image size dims
  let size = await requestImageSize(image['url'])
  expect(size.width).toBe(bigImageWidth)
  expect(size.height).toBe(bigImageHeight)
  let size2 = await requestImageSize(url)
  expect(size2.width).toBe(bigImageWidth)
  expect(size2.height).toBe(bigImageHeight)

  // check the 64p image size dims
  size = await requestImageSize(image['url64p'])
  expect(size.width).toBe(114)
  expect(size.height).toBeLessThan(64)
  size2 = await requestImageSize(url64p)
  expect(size2.width).toBe(114)
  expect(size2.height).toBeLessThan(64)

  // check the 480p image size dims
  size = await requestImageSize(image['url480p'])
  expect(size.width).toBe(854)
  expect(size.height).toBeLessThan(480)
  size2 = await requestImageSize(url480p)
  expect(size2.width).toBe(854)
  expect(size2.height).toBeLessThan(480)

  // check the 1080p image size dims
  size = await requestImageSize(image['url1080p'])
  expect(size.width).toBe(1920)
  expect(size.height).toBeLessThan(1080)
  size2 = await requestImageSize(url1080p)
  expect(size2.width).toBe(1920)
  expect(size2.height).toBeLessThan(1080)

  // check the 4k image size dims
  size = await requestImageSize(image['url4k'])
  expect(size.width).toBe(3840)
  expect(size.height).toBeLessThan(2160)
  size2 = await requestImageSize(url4k)
  expect(size2.width).toBe(3840)
  expect(size2.height).toBeLessThan(2160)
})
