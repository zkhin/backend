/* eslint-env jest */

/**
 * This whole file is DEPRECATED.
 * To be removed when the mediaUploads argument to Mutation.addPost
 * goes away.
 */

const fs = require('fs')
const path = require('path')
const requestImageSize = require('request-image-size')
const rp = require('request-promise-native')
const uuidv4 = require('uuid/v4')

const cognito = require('../utils/cognito.js')
const misc = require('../utils/misc.js')
const { mutations, queries } = require('../schema')

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
  await expect(client.mutate({mutation: mutations.addPostTwoMedia, variables}))
    .rejects.toThrow(/ClientError: .* add post with more than one media/)

  // verify the post did not get created
  let resp = await client.query({query: queries.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']).toBeNull()
})


test('Uploading image sets width, height and colors', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // upload an image post
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let variables = {postId, mediaId}
  let resp = await ourClient.mutate({mutation: mutations.addPostMediaUploads, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['image']).toBeNull()
  const uploadUrl = resp['data']['addPost']['imageUploadUrl']

  // double check the image post
  variables = {postId}
  resp = await ourClient.query({query: queries.post, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['image']).toBeNull()

  // upload the first of those images, give the s3 trigger a second to fire
  await rp.put({url: uploadUrl, headers: jpgHeaders, body: imageData})
  await misc.sleepUntilPostCompleted(ourClient, postId)

  // check width, height and colors are now set
  variables = {postId}
  resp = await ourClient.query({query: queries.post, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['image']['height']).toBe(imageHeight)
  expect(resp['data']['post']['image']['width']).toBe(imageWidth)
  expect(resp['data']['post']['image']['colors']).toHaveLength(5)
  expect(resp['data']['post']['image']['colors'][0]['r']).toBeTruthy()
  expect(resp['data']['post']['image']['colors'][0]['g']).toBeTruthy()
  expect(resp['data']['post']['image']['colors'][0]['b']).toBeTruthy()
})


test('Uploading png image results in error', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // create a pending image post
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: mutations.addPostMediaUploads, variables: {postId, mediaId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postStatus']).toBe('PENDING')
  const uploadUrl = resp['data']['addPost']['imageUploadUrl']

  // upload a png, give the s3 trigger a second to fire
  await rp.put({url: uploadUrl, headers: pngHeaders, body: pngData})
  await misc.sleep(5000)

  // check that post ended up in an ERROR state
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['postStatus']).toBe('ERROR')
})


test('Thumbnails built on successful upload', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // create a pending image post
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: mutations.addPostMediaUploads, variables: {postId, mediaId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postStatus']).toBe('PENDING')
  const uploadUrl = resp['data']['addPost']['imageUploadUrl']

  // upload a big jpeg, give the s3 trigger a second to fire
  await rp.put({url: uploadUrl, headers: jpgHeaders, body: bigImageData})
  await misc.sleep(5000)  // big jpeg, so takes at least a few seconds to process
  await misc.sleepUntilPostCompleted(ourClient, postId)

  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  const image = resp['data']['post']['image']
  expect(image).toBeTruthy()

  // check the native image size dims
  let size = await requestImageSize(image['url'])
  expect(size.width).toBe(bigImageWidth)
  expect(size.height).toBe(bigImageHeight)

  // check the 64p image size dims
  size = await requestImageSize(image['url64p'])
  expect(size.width).toBe(114)
  expect(size.height).toBeLessThan(64)

  // check the 480p image size dims
  size = await requestImageSize(image['url480p'])
  expect(size.width).toBe(854)
  expect(size.height).toBeLessThan(480)

  // check the 1080p image size dims
  size = await requestImageSize(image['url1080p'])
  expect(size.width).toBe(1920)
  expect(size.height).toBeLessThan(1080)

  // check the 4k image size dims
  size = await requestImageSize(image['url4k'])
  expect(size.width).toBe(3840)
  expect(size.height).toBeLessThan(2160)
})
