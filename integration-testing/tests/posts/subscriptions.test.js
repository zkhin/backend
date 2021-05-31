const got = require('got')
const {v4: uuidv4} = require('uuid')

const {cognito, generateRandomJpeg, sleep} = require('../../utils')
const {mutations, subscriptions} = require('../../schema')

const imageHeaders = {'Content-Type': 'image/jpeg'}
const imageBytes = generateRandomJpeg(8, 8)
const imageData = new Buffer.from(imageBytes).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('POST_COMPLETED notification triggers correctly posts', async () => {
  const {client, userId} = await loginCache.getCleanLogin()

  // we subscribe to notifications
  const handlers = []
  const sub = await client.subscribe({query: subscriptions.onNotification, variables: {userId}}).subscribe({
    next: ({data: {onNotification: notification}}) => {
      if (notification.type.startsWith('POST_')) {
        const handler = handlers.shift()
        expect(handler).toBeDefined()
        handler(notification)
      }
    },
    error: (resp) => expect(`Subscription error: ${resp}`).toBeNull(),
  })
  const subInitTimeout = sleep('subTimeout')
  await sleep('subInit')

  // create a text-only post, verify it completes automatically and we are notified
  let nextNotification = new Promise((resolve) => handlers.push(resolve))
  const postId1 = uuidv4()
  await client
    .mutate({mutation: mutations.addPost, variables: {postId: postId1, postType: 'TEXT_ONLY', text: 'lore'}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId1)
      expect(post.postStatus).toBe('COMPLETED')
    })
  await nextNotification.then((notification) => {
    expect(notification.type).toBe('POST_COMPLETED')
    expect(notification.postId).toBe(postId1)
  })

  // create an image post, upload the image data along with post, verify
  nextNotification = new Promise((resolve) => handlers.push(resolve))
  const postId2 = uuidv4()
  await client
    .mutate({mutation: mutations.addPost, variables: {postId: postId2, imageData}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId2)
      expect(post.postStatus).toBe('COMPLETED')
    })
  await nextNotification.then((notification) => {
    expect(notification.type).toBe('POST_COMPLETED')
    expect(notification.postId).toBe(postId2)
  })

  // archive a post, then restore it (verify no spurious notification)
  await client
    .mutate({mutation: mutations.archivePost, variables: {postId: postId1}})
    .then(({data: {archivePost: post}}) => expect(post.postStatus).toBe('ARCHIVED'))
  await client
    .mutate({mutation: mutations.restoreArchivedPost, variables: {postId: postId1}})
    .then(({data: {restoreArchivedPost: post}}) => expect(post.postStatus).toBe('COMPLETED'))

  // create another image post, don't upload the image data yet
  const postId3 = uuidv4()
  const uploadUrl = await client
    .mutate({mutation: mutations.addPost, variables: {postId: postId3}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId3)
      expect(post.postStatus).toBe('PENDING')
      return post.imageUploadUrl
    })

  // upload the image data to cloudfront, verify notification received
  nextNotification = new Promise((resolve) => handlers.push(resolve))
  await got.put(uploadUrl, {headers: imageHeaders, body: imageBytes})
  await nextNotification.then((notification) => {
    expect(notification.type).toBe('POST_COMPLETED')
    expect(notification.postId).toBe(postId3)
  })

  // shut down the subscription
  sub.unsubscribe()
  await subInitTimeout
})

test('POST_ERROR notification triggers correctly posts', async () => {
  const {client, userId} = await loginCache.getCleanLogin()

  // we subscribe to notifications
  const handlers = []
  const sub = await client.subscribe({query: subscriptions.onNotification, variables: {userId}}).subscribe({
    next: ({data: {onNotification: notification}}) => {
      if (notification.type.startsWith('POST_')) {
        const handler = handlers.shift()
        expect(handler).toBeDefined()
        handler(notification)
      }
    },
    error: (resp) => expect(`Subscription error: ${resp}`).toBeNull(),
  })
  const subInitTimeout = sleep('subTimeout')
  await sleep('subInit')

  // create an image post, upload invalid image data along with post, verify
  let nextNotification = new Promise((resolve) => handlers.push(resolve))
  const postId1 = uuidv4()
  await client
    .mutate({mutation: mutations.addPost, variables: {postId: postId1, imageData: 'invalid-image-data'}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId1)
      expect(post.postStatus).toBe('ERROR')
    })
  await nextNotification.then((notification) => {
    expect(notification.type).toBe('POST_ERROR')
    expect(notification.postId).toBe(postId1)
  })

  // create another image post, don't upload the image data yet
  const postId2 = uuidv4()
  const uploadUrl = await client
    .mutate({mutation: mutations.addPost, variables: {postId: postId2}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId2)
      expect(post.postStatus).toBe('PENDING')
      return post.imageUploadUrl
    })

  // upload some invalid image data to cloudfront, verify
  nextNotification = new Promise((resolve) => handlers.push(resolve))
  await got.put(uploadUrl, {headers: imageHeaders, body: 'other-invalid-image-data'})
  await nextNotification.then((notification) => {
    expect(notification.type).toBe('POST_ERROR')
    expect(notification.postId).toBe(postId2)
  })

  // shut down the subscription
  sub.unsubscribe()
  await subInitTimeout
})
