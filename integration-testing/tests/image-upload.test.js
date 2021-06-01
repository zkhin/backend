import fs from 'fs'
import got from 'got'
import requestImageSize from 'request-image-size'
import {v4 as uuidv4} from 'uuid'

import {cognito, eventually, fixturePath} from '../utils'
import {mutations, queries} from '../schema'

const jpgHeaders = {'Content-Type': 'image/jpeg'}
const pngHeaders = {'Content-Type': 'image/png'}
const heicHeaders = {'Content-Type': 'image/heic'}

const imageData = fs.readFileSync(fixturePath('grant.jpg'))
const imageHeight = 320
const imageWidth = 240

const bigImageData = fs.readFileSync(fixturePath('big-blank.jpg'))
const bigImageHeight = 2000
const bigImageWidth = 4000

const heicImageData = fs.readFileSync(fixturePath('IMG_0265.HEIC'))
const heicImageHeight = 3024
const heicImageWidth = 4032

const pngData = fs.readFileSync(fixturePath('grant.png'))
const pngHeight = 320
const pngWidth = 240
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Uploading image sets width, height and colors', async () => {
  const {client} = await loginCache.getCleanLogin()

  // upload an image post
  const postId = uuidv4()
  const uploadUrl = await client
    .mutate({mutation: mutations.addPost, variables: {postId}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId)
      expect(post.image).toBeNull()
      expect(post.imageUploadUrl).toBeTruthy()
      return post.imageUploadUrl
    })

  // double check the image post
  await client.query({query: queries.post, variables: {postId}}).then(({data: {post}}) => {
    expect(post.postId).toBe(postId)
    expect(post.image).toBeNull()
  })

  // upload the first of those images
  await got.put(uploadUrl, {headers: jpgHeaders, body: imageData})

  // check width, height and colors are now set
  await eventually(async () => {
    const {data} = await client.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.postStatus).toBe('COMPLETED')
    expect(data.post.image.height).toBe(imageHeight)
    expect(data.post.image.width).toBe(imageWidth)
    expect(data.post.image.colors).toHaveLength(5)
    expect(data.post.image.colors[0].r).toBeTruthy()
    expect(data.post.image.colors[0].g).toBeTruthy()
    expect(data.post.image.colors[0].b).toBeTruthy()
  })
})

test('Uploading png image', async () => {
  const {client} = await loginCache.getCleanLogin()

  // create a pending image post
  const postId = uuidv4()
  const uploadUrl = await client
    .mutate({mutation: mutations.addPost, variables: {postId}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId)
      expect(post.postStatus).toBe('PENDING')
      expect(post.imageUploadUrl).toBeTruthy()
      return post.imageUploadUrl
    })

  // upload a png
  await got.put(uploadUrl, {headers: pngHeaders, body: pngData})

  // check that post ended up in an COMPLETED state
  await eventually(async () => {
    const {data} = await client.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.postStatus).toBe('COMPLETED')
    expect(data.post.image.height).toBe(pngHeight)
    expect(data.post.image.width).toBe(pngWidth)
    expect(data.post.image.colors).toHaveLength(5)
    expect(data.post.image.colors[0].r).toBeTruthy()
    expect(data.post.image.colors[0].g).toBeTruthy()
    expect(data.post.image.colors[0].b).toBeTruthy()
  })
})

test('Upload heic image', async () => {
  const {client} = await loginCache.getCleanLogin()

  // create a pending image post
  const postId = uuidv4()
  const uploadUrl = await client
    .mutate({mutation: mutations.addPost, variables: {postId, imageFormat: 'HEIC'}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId)
      expect(post.postStatus).toBe('PENDING')
      expect(post.imageUploadUrl).toContain('native.heic')
      return post.imageUploadUrl
    })

  // upload a heic
  await got.put(uploadUrl, {headers: heicHeaders, body: heicImageData})

  // check that post completed and generated all thumbnails ok
  const image = await eventually(async () => {
    const {data} = await client.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.postStatus).toBe('COMPLETED')
    expect(data.post.isVerified).toBe(true)
    expect(data.post.image).toBeTruthy()
    return data.post.image
  })

  // check the native image size dims
  await requestImageSize(image.url).then(({width, height}) => {
    expect(width).toBe(heicImageWidth)
    expect(height).toBe(heicImageHeight)
  })

  // check the 64p image size dims
  await requestImageSize(image.url64p).then(({width, height}) => {
    expect(width).toBeLessThan(114)
    expect(height).toBe(64)
  })

  // check the 480p image size dims
  await requestImageSize(image.url480p).then(({width, height}) => {
    expect(width).toBeLessThan(854)
    expect(height).toBe(480)
  })

  // check the 1080p image size dims
  await requestImageSize(image.url1080p).then(({width, height}) => {
    expect(width).toBeLessThan(1920)
    expect(height).toBe(1080)
  })

  // check the 4k image size dims
  await requestImageSize(image.url4k).then(({width, height}) => {
    expect(width).toBeLessThan(3840)
    expect(height).toBe(2160)
  })
})

test('Thumbnails built on successful upload', async () => {
  const {client} = await loginCache.getCleanLogin()

  // create a pending image post
  const postId = uuidv4()
  const uploadUrl = await client
    .mutate({mutation: mutations.addPost, variables: {postId}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId)
      expect(post.postStatus).toBe('PENDING')
      expect(post.imageUploadUrl).toBeTruthy()
      return post.imageUploadUrl
    })

  // upload a big jpeg
  await got.put(uploadUrl, {headers: jpgHeaders, body: bigImageData})

  const image = await eventually(async () => {
    const {data} = await client.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.image).toBeTruthy()
    return data.post.image
  })

  // check the native image size dims
  await requestImageSize(image.url).then(({width, height}) => {
    expect(width).toBe(bigImageWidth)
    expect(height).toBe(bigImageHeight)
  })

  // check the 64p image size dims
  await requestImageSize(image.url64p).then(({width, height}) => {
    expect(width).toBe(114)
    expect(height).toBeLessThan(64)
  })

  // check the 480p image size dims
  await requestImageSize(image.url480p).then(({width, height}) => {
    expect(width).toBe(854)
    expect(height).toBeLessThan(480)
  })

  // check the 1080p image size dims
  await requestImageSize(image.url1080p).then(({width, height}) => {
    expect(width).toBe(1920)
    expect(height).toBeLessThan(1080)
  })

  // check the 4k image size dims
  await requestImageSize(image.url4k).then(({width, height}) => {
    expect(width).toBe(3840)
    expect(height).toBeLessThan(2160)
  })
})
