import fs from 'fs'
import got from 'got'
import requestImageSize from 'request-image-size'
import {v4 as uuidv4} from 'uuid'

import {cognito, eventually, fixturePath} from '../../utils'
import {mutations, queries} from '../../schema'

const heicHeight = 3024
const heicWidth = 4032
const heicBytes = fs.readFileSync(fixturePath('IMG_0265.HEIC'))
const heicData = new Buffer.from(heicBytes).toString('base64')
const heicHeaders = {'Content-Type': 'image/heic'}
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Invalid heic crops, direct gql data upload', async () => {
  const {client} = await loginCache.getCleanLogin()

  // can't crop negative
  const postId1 = uuidv4()
  await expect(
    client.mutate({
      mutation: mutations.addPost,
      variables: {
        postId: postId1,
        imageData: heicData,
        imageFormat: 'HEIC',
        crop: {upperLeft: {x: 1, y: -1}, lowerRight: {x: heicWidth - 1, y: heicHeight - 1}},
      },
    }),
  ).rejects.toThrow(/ClientError: .* cannot be negative/)

  // can't down to zero area
  const postId2 = uuidv4()
  await expect(
    client.mutate({
      mutation: mutations.addPost,
      variables: {
        postId: postId2,
        imageData: heicData,
        imageFormat: 'HEIC',
        crop: {upperLeft: {x: 100, y: 1}, lowerRight: {x: 100, y: heicHeight - 1}},
      },
    }),
  ).rejects.toThrow(/ClientError: .* must be strictly greater than /)

  // can't crop wider than post is. Post gets created and left in ERROR state in backend
  const postId3 = uuidv4()
  await client
    .mutate({
      mutation: mutations.addPost,
      variables: {
        postId: postId3,
        imageData: heicData,
        imageFormat: 'HEIC',
        crop: {upperLeft: {x: 1, y: 1}, lowerRight: {x: heicWidth + 1, y: heicHeight - 1}},
      },
    })
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId3)
      expect(post.postStatus).toBe('ERROR')
    })

  // double check DB state on all those posts
  await client
    .query({query: queries.postsThree, variables: {postId1, postId2, postId3}})
    .then(({data: {post1, post2, post3}}) => {
      expect(post1).toBeNull()
      expect(post2).toBeNull()
      expect(post3.postId).toBe(postId3)
      expect(post3.postStatus).toBe('ERROR')
    })
})

test('Invalid heic crops, upload via cloudfront', async () => {
  const {client} = await loginCache.getCleanLogin()

  // add a post that with a crop that's too wide
  const postId1 = uuidv4()
  const uploadUrl = await client
    .mutate({
      mutation: mutations.addPost,
      variables: {
        postId: postId1,
        imageFormat: 'HEIC',
        crop: {upperLeft: {x: 1, y: 1}, lowerRight: {x: heicWidth + 1, y: heicHeight - 1}},
      },
    })
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId1)
      expect(post.postStatus).toBe('PENDING')
      expect(post.imageUploadUrl).toBeTruthy()
      return post.imageUploadUrl
    })
  await got.put(uploadUrl, {body: heicBytes, headers: heicHeaders})
  await eventually(async () => {
    const {data} = await client.query({query: queries.post, variables: {postId: postId1}})
    expect(data.post.postStatus).toBe('ERROR')
  })

  // can't crop negative
  const postId2 = uuidv4()
  await expect(
    client.mutate({
      mutation: mutations.addPost,
      variables: {
        postId: postId2,
        imageFormat: 'HEIC',
        crop: {upperLeft: {x: 1, y: -1}, lowerRight: {x: heicWidth - 1, y: heicHeight - 1}},
      },
    }),
  ).rejects.toThrow(/ClientError: .* cannot be negative/)

  // can't down to zero area
  const postId3 = uuidv4()
  await expect(
    client.mutate({
      mutation: mutations.addPost,
      variables: {
        postId: postId3,
        imageFormat: 'HEIC',
        crop: {upperLeft: {x: 100, y: 1}, lowerRight: {x: 100, y: heicHeight - 1}},
      },
    }),
  ).rejects.toThrow(/ClientError: .* must be strictly greater than /)

  // check DB state on all those posts
  await client
    .query({query: queries.postsThree, variables: {postId1, postId2, postId3}})
    .then(({data: {post1, post2, post3}}) => {
      expect(post1.postStatus).toBe('ERROR')
      expect(post2).toBeNull()
      expect(post3).toBeNull()
    })
})

test('Valid heic crop, direct upload via gql', async () => {
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
        crop: {upperLeft: {x: 1, y: 2}, lowerRight: {x: 3, y: 5}},
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
    expect(width).toBe(2)
    expect(height).toBe(3)
  })

  // check size of the 4K thumbnail
  await requestImageSize(postImage.url4k).then(({width, height}) => {
    expect(width).toBe(2)
    expect(height).toBe(3)
  })
})

test('Valid heic crop, upload via cloudfront', async () => {
  const {client} = await loginCache.getCleanLogin()

  // add the post
  const postId = uuidv4()
  const uploadUrl = await client
    .mutate({
      mutation: mutations.addPost,
      variables: {
        postId,
        imageFormat: 'HEIC',
        crop: {
          upperLeft: {x: heicWidth / 4, y: heicHeight / 4},
          lowerRight: {x: (heicWidth * 3) / 4, y: (heicHeight * 3) / 4},
        },
      },
    })
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId)
      expect(post.postStatus).toBe('PENDING')
      expect(post.imageUploadUrl).toBeTruthy()
      return post.imageUploadUrl
    })
  await got.put(uploadUrl, {body: heicBytes, headers: heicHeaders})

  // retrieve the post object, check some image sizes
  const postImage = await eventually(async () => {
    const {data} = await client.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.postStatus).toBe('COMPLETED')
    expect(data.post.image.url).toBeTruthy()
    return data.post.image
  })
  await requestImageSize(postImage.url).then(({width, height}) => {
    expect(width).toBe(heicWidth / 2)
    expect(height).toBe(heicHeight / 2)
  })
  await requestImageSize(postImage.url4k).then(({width, height}) => {
    expect(width).toBe(heicWidth / 2)
    expect(height).toBe(heicHeight / 2)
  })
})
