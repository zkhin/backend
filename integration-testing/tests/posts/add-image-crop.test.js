/* eslint-env jest */

const exifReader = require('exif-reader')
const fs = require('fs')
const path = require('path')
const requestImageSize = require('request-image-size')
const rp = require('request-promise-native')
const sharp = require('sharp')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito')
const misc = require('../../utils/misc')
const {mutations, queries} = require('../../schema')

const jpegHeight = 32
const jpegWidth = 64
const jpegBytes = misc.generateRandomJpeg(jpegWidth, jpegHeight)
const jpegData = new Buffer.from(jpegBytes).toString('base64')
const jpegHeaders = {'Content-Type': 'image/jpeg'}

const grantBytes = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg'))
const grantData = new Buffer.from(grantBytes).toString('base64')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Invalid jpeg crops, direct gql data upload', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const imageData = jpegData

  // can't crop negative
  let postId = uuidv4()
  let crop = {upperLeft: {x: 1, y: -1}, lowerRight: {x: jpegWidth - 1, y: jpegHeight - 1}}
  await expect(
    ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData, crop}}),
  ).rejects.toThrow(/ClientError: .* cannot be negative/)
  let resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.data.post).toBeNull()

  // can't down to zero area
  postId = uuidv4()
  crop = {upperLeft: {x: 100, y: 1}, lowerRight: {x: 100, y: jpegHeight - 1}}
  await expect(
    ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData, crop}}),
  ).rejects.toThrow(/ClientError: .* must be strictly greater than /)
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.data.post).toBeNull()

  // can't crop wider than post is. Post gets created and left in ERROR state in backend
  postId = uuidv4()
  crop = {upperLeft: {x: 1, y: 1}, lowerRight: {x: jpegWidth + 1, y: jpegHeight - 1}}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData, crop}})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('ERROR')
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.postStatus).toBe('ERROR')
})

test('Invalid jpeg crops, upload via cloudfront', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // can't crop negative
  let postId = uuidv4()
  let crop = {upperLeft: {x: 1, y: -1}, lowerRight: {x: jpegWidth - 1, y: jpegHeight - 1}}
  await expect(ourClient.mutate({mutation: mutations.addPost, variables: {postId, crop}})).rejects.toThrow(
    /ClientError: .* cannot be negative/,
  )
  let resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.data.post).toBeNull()

  // add a post that with a crop that's too wide
  postId = uuidv4()
  crop = {upperLeft: {x: 1, y: 1}, lowerRight: {x: jpegWidth + 1, y: jpegHeight - 1}}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, crop}})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('PENDING')
  let uploadUrl = resp.data.addPost.imageUploadUrl
  expect(uploadUrl).toBeTruthy()

  // upload the image data to cloudfront
  await rp.put({url: uploadUrl, headers: jpegHeaders, body: jpegBytes})
  await misc.sleep(5 * 1000) // enough time to error our

  // check the post is now in an error state
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.postStatus).toBe('ERROR')

  // can't down to zero area
  postId = uuidv4()
  crop = {upperLeft: {x: 100, y: 1}, lowerRight: {x: 100, y: jpegHeight - 1}}
  await expect(ourClient.mutate({mutation: mutations.addPost, variables: {postId, crop}})).rejects.toThrow(
    /ClientError: .* must be strictly greater than /,
  )
})

test('Valid jpeg crop, direct upload via gql', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // add the post
  const postId = uuidv4()
  const crop = {upperLeft: {x: 1, y: 2}, lowerRight: {x: 3, y: 5}}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData: jpegData, crop}})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  let urlNative = resp.data.addPost.image.url
  let url4k = resp.data.addPost.image.url4k
  expect(urlNative).toBeTruthy()
  expect(url4k).toBeTruthy()

  // check size of the native image
  let size = await requestImageSize(urlNative)
  expect(size.width).toBe(2)
  expect(size.height).toBe(3)

  // check size of the 4K thumbnail
  size = await requestImageSize(url4k)
  expect(size.width).toBe(2)
  expect(size.height).toBe(3)
})

test('Valid jpeg crop, upload via cloudfront', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // add the post
  const postId = uuidv4()
  const crop = {
    upperLeft: {x: jpegWidth / 4, y: jpegHeight / 4},
    lowerRight: {x: (jpegWidth * 3) / 4, y: (jpegHeight * 3) / 4},
  }
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, crop}})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('PENDING')
  let uploadUrl = resp.data.addPost.imageUploadUrl
  expect(uploadUrl).toBeTruthy()

  // upload the image data to cloudfront
  await rp.put({url: uploadUrl, headers: jpegHeaders, body: jpegBytes})
  await misc.sleepUntilPostCompleted(ourClient, postId)

  // retrieve the post object
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.postStatus).toBe('COMPLETED')
  let urlNative = resp.data.post.image.url
  let url4k = resp.data.post.image.url4k
  expect(urlNative).toBeTruthy()
  expect(url4k).toBeTruthy()

  // check size of the native image
  let size = await requestImageSize(urlNative)
  expect(size.width).toBe(jpegWidth / 2)
  expect(size.height).toBe(jpegHeight / 2)

  // check size of the 4K thumbnail
  size = await requestImageSize(url4k)
  expect(size.width).toBe(jpegWidth / 2)
  expect(size.height).toBe(jpegHeight / 2)
})

test('Valid jpeg crop, metadata preserved', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // pull exif data (only exif) from the original image
  const orgExif = await sharp(grantBytes)
    .metadata()
    .then(({exif}) => {
      return exifReader(exif)
    })
  expect(orgExif).toBeTruthy()

  // add the post with a crop
  const postId = uuidv4()
  const crop = {upperLeft: {x: 10, y: 20}, lowerRight: {x: 30, y: 40}}
  let resp = await ourClient.mutate({
    mutation: mutations.addPost,
    variables: {postId, imageData: grantData, crop},
  })
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  let urlNative = resp.data.addPost.image.url
  expect(urlNative).toBeTruthy()

  // get the exif data of the cropped image
  const croppedBytes = await rp.get({uri: urlNative, encoding: null})
  const newExif = await sharp(croppedBytes)
    .metadata()
    .then(({exif}) => {
      return exifReader(exif)
    })

  // make sure exif data hasn't changed
  expect(newExif).toEqual(orgExif)

  // Want to write the cropped image out to a file? here's how to do it
  // fs.writeFile('./cropped.jpeg', croppedBytes)
})
