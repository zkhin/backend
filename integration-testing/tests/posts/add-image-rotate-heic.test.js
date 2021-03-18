const fs = require('fs')
const got = require('got')
const path = require('path')
const requestImageSize = require('request-image-size')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito')
const misc = require('../../utils/misc')
const {mutations, queries} = require('../../schema')

const heicHeight = 3024
const heicWidth = 4032
const heicBytes = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'IMG_0265.HEIC'))
const heicData = new Buffer.from(heicBytes).toString('base64')
const heicHeaders = {'Content-Type': 'image/heic'}
const loginCache = new cognito.AppSyncLoginCache()
jest.retryTimes(1)

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Invalid heic rotate, direct gql data upload', async () => {
  const {client} = await loginCache.getCleanLogin()

  // can't rotate
  const postId1 = uuidv4()
  await expect(
    client.mutate({
      mutation: mutations.addPost,
      variables: {
        postId: postId1,
        imageData: heicData,
        imageFormat: 'HEIC',
        rotate: 91,
      },
    }),
  ).rejects.toThrow(/ClientError: Invalid rotate angle .*/)
})

test('Valid heic rotate, direct upload via gql', async () => {
  const {client} = await loginCache.getCleanLogin()

  // add the post
  const postId = uuidv4()
  const postImage = await client
    .mutate({
      mutation: mutations.addPost,
      variables: {
        postId,
        imageData: heicData,
        imageFormat: 'HEIC',
        rotate: 90,
      },
    })
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId)
      expect(post.postStatus).toBe('COMPLETED')
      expect(post.image.url).toBeTruthy()
      return post.image
    })

  // check size of the native image
  await requestImageSize(postImage.url).then(({width, height}) => {
    // width and hegith should be swapped
    expect(width).toBe(heicHeight)
    expect(height).toBe(heicWidth)
  })
})

test('Valid heic rotate, upload via cloudfront', async () => {
  const {client} = await loginCache.getCleanLogin()

  // add the post
  const postId = uuidv4()
  const uploadUrl = await client
    .mutate({
      mutation: mutations.addPost,
      variables: {
        postId,
        imageFormat: 'HEIC',
        rotate: 90,
      },
    })
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId)
      expect(post.postStatus).toBe('PENDING')
      expect(post.imageUploadUrl).toBeTruthy()
      return post.imageUploadUrl
    })
  await got.put(uploadUrl, {body: heicBytes, headers: heicHeaders})
  await misc.sleepUntilPostProcessed(client, postId)

  // retrieve the post object, check some image sizes
  const postImage = await client.query({query: queries.post, variables: {postId}}).then(({data: {post}}) => {
    expect(post.postId).toBe(postId)
    expect(post.postStatus).toBe('COMPLETED')
    expect(post.image.url).toBeTruthy()
    return post.image
  })
  await requestImageSize(postImage.url).then(({width, height}) => {
    expect(width).toBe(heicHeight)
    expect(height).toBe(heicWidth)
  })
})

test('Valid heic rotate, crop, direct upload via gql', async () => {
  const {client} = await loginCache.getCleanLogin()

  // add the post
  const postId = uuidv4()
  const postImage = await client
    .mutate({
      mutation: mutations.addPost,
      variables: {
        postId,
        imageData: heicData,
        imageFormat: 'HEIC',
        crop: {upperLeft: {x: 0, y: 0}, lowerRight: {x: heicHeight, y: heicWidth}},
        rotate: 90,
      },
    })
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId)
      expect(post.postStatus).toBe('COMPLETED')
      expect(post.image.url).toBeTruthy()
      return post.image
    })

  // check size of the native image
  await requestImageSize(postImage.url).then(({width, height}) => {
    expect(width).toBe(heicHeight)
    expect(height).toBe(heicWidth)
  })
})
