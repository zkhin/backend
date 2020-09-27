const got = require('got')
const uuidv4 = require('uuid/v4')
// the aws-appsync-subscription-link pacakge expects WebSocket to be globaly defined, like in the browser
global.WebSocket = require('ws')

const cognito = require('../../utils/cognito')
const misc = require('../../utils/misc')
const {mutations, subscriptions} = require('../../schema')

const imageHeaders = {'Content-Type': 'image/jpeg'}
const imageBytes = misc.generateRandomJpeg(8, 8)
const imageData = new Buffer.from(imageBytes).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()
jest.retryTimes(1)

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('POST_COMPLETED notification triggers correctly posts', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()

  // we subscribe to notifications
  let notificationsCount = 0
  const notificationHandlers = []
  const notifications = [
    new Promise((resolve, reject) => notificationHandlers.push({resolve, reject})),
    new Promise((resolve, reject) => notificationHandlers.push({resolve, reject})),
    new Promise((resolve, reject) => notificationHandlers.push({resolve, reject})),
  ]
  const sub = await ourClient
    .subscribe({query: subscriptions.onNotification, variables: {userId: ourUserId}})
    .subscribe({
      next: ({data}) => {
        if (data.onNotification.type.startsWith('POST_')) {
          notificationsCount += 1
          notificationHandlers.shift().resolve(data.onNotification)
        }
      },
      error: (resp) => notificationHandlers.shift().reject(resp), // necessry? could this just throw an error?
    })
  const subInitTimeout = misc.sleep(15000) // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541
  await misc.sleep(2000) // let the subscription initialize

  // we create a text-only post, it completes automatically
  const postId1 = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId: postId1, postType: 'TEXT_ONLY', text: 'lore'}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId1)
      expect(post.postStatus).toBe('COMPLETED')
    })

  // check we received notification for that post
  await notifications.shift().then((notif) => {
    expect(notif.type).toBe('POST_COMPLETED')
    expect(notif.postId).toBe(postId1)
    expect((notificationsCount -= 1)).toBe(0)
  })

  // we create an image post, upload the image data along with post creation to complete it immediately
  const postId2 = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId: postId2, imageData}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId2)
      expect(post.postStatus).toBe('COMPLETED')
    })

  // check we received a notification for that post
  await notifications.shift().then((notif) => {
    expect(notif.type).toBe('POST_COMPLETED')
    expect(notif.postId).toBe(postId2)
    expect((notificationsCount -= 1)).toBe(0)
  })

  // archive a post, then restore it (trying to generate a spurious fire)
  await ourClient
    .mutate({mutation: mutations.archivePost, variables: {postId: postId1}})
    .then(({data: {archivePost: post}}) => expect(post.postStatus).toBe('ARCHIVED'))
  await ourClient
    .mutate({mutation: mutations.restoreArchivedPost, variables: {postId: postId1}})
    .then(({data: {restoreArchivedPost: post}}) => expect(post.postStatus).toBe('COMPLETED'))

  // create another image post, don't upload the image data yet
  const postId3 = uuidv4()
  const uploadUrl = await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId: postId3}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId3)
      expect(post.postStatus).toBe('PENDING')
      return post.imageUploadUrl
    })

  // check we have not received any notifications
  await misc.sleep(5 * 1000).then(() => expect(notificationsCount).toBe(0))

  // upload the image data to cloudfront
  await got.put(uploadUrl, {headers: imageHeaders, body: imageBytes})

  // check we received a notification for that post
  await notifications.shift().then((notif) => {
    expect(notif.type).toBe('POST_COMPLETED')
    expect(notif.postId).toBe(postId3)
    expect((notificationsCount -= 1)).toBe(0)
  })

  // shut down the subscription
  sub.unsubscribe()
  await subInitTimeout
})

test('POST_ERROR notification triggers correctly posts', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()

  // we subscribe to notifications
  let notificationsCount = 0
  const notificationHandlers = []
  const notifications = [
    new Promise((resolve, reject) => notificationHandlers.push({resolve, reject})),
    new Promise((resolve, reject) => notificationHandlers.push({resolve, reject})),
  ]
  const sub = await ourClient
    .subscribe({query: subscriptions.onNotification, variables: {userId: ourUserId}})
    .subscribe({
      next: ({data}) => {
        if (data.onNotification.type.startsWith('POST_')) {
          notificationsCount += 1
          notificationHandlers.shift().resolve(data.onNotification)
        }
      },
      error: (resp) => notificationHandlers.shift().reject(resp), // necessry? could this just throw an error?
    })
  const subInitTimeout = misc.sleep(15000) // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541
  await misc.sleep(2000) // let the subscription initialize

  // we create an image post, upload invalid image data along with post creation to send it to ERROR it immediately
  const postId1 = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId: postId1, imageData: 'invalid-image-data'}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId1)
      expect(post.postStatus).toBe('ERROR')
    })

  // check we received a notification for that post
  await notifications.shift().then((notif) => {
    expect(notif.type).toBe('POST_ERROR')
    expect(notif.postId).toBe(postId1)
    expect((notificationsCount -= 1)).toBe(0)
  })

  // create another image post, don't upload the image data yet
  const postId3 = uuidv4()
  const uploadUrl = await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId: postId3}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId3)
      expect(post.postStatus).toBe('PENDING')
      return post.imageUploadUrl
    })

  // check we have not received any notifications
  await misc.sleep(5 * 1000).then(() => expect(notificationsCount).toBe(0))

  // upload some invalid image data to cloudfront
  await got.put(uploadUrl, {headers: imageHeaders, body: 'other-invalid-image-data'})

  // check we received a notification for that post
  await notifications.shift().then((notif) => {
    expect(notif.type).toBe('POST_ERROR')
    expect(notif.postId).toBe(postId3)
    expect((notificationsCount -= 1)).toBe(0)
  })

  // shut down the subscription
  sub.unsubscribe()
  await subInitTimeout
})

test('Post message triggers cannot be called from external graphql client', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()

  // create an image post in pending state
  const postId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, postType: 'IMAGE'}})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postType).toBe('IMAGE')
  expect(resp.data.addPost.postStatus).toBe('PENDING')

  // verify we can't call the trigger method, even with well-formed input
  const input = {
    userId: ourUserId,
    type: 'COMPLETED',
    postId,
    postStatus: 'COMPLETED',
    isVerified: false,
  }
  await expect(
    ourClient.mutate({mutation: mutations.triggerPostNotification, variables: {input}}),
  ).rejects.toThrow(/ClientError: Access denied/)
})

test('Cannot subscribe to other users notifications', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // verify we cannot subscribe to their messages
  // Note: there doesn't seem to be any error thrown at the time of subscription, it's just that
  // the subscription next() method is never triggered
  const notifications = []
  await ourClient
    .subscribe({query: subscriptions.onPostNotification, variables: {userId: theirUserId}})
    .subscribe({
      next: (resp) => notifications.push(resp),
      error: (resp) => console.log(resp),
    })

  // they create an image post, complete it
  const postId = uuidv4()
  let variables = {postId, imageData, takenInReal: true}
  let resp = await theirClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // wait for some messages to show up, ensure none did
  await misc.sleep(5000)
  expect(notifications).toEqual([])

  // we don't unsubscribe from the subscription because
  //  - it's not actually active, although I have yet to find a way to expect() that
  //  - unsubcribing results in the AWS SDK throwing errors
})

test('Format for COMPLETED message notifications', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()

  // we subscribe to post notifications
  const ourNotifications = []
  const ourSub = await ourClient
    .subscribe({query: subscriptions.onPostNotification, variables: {userId: ourUserId}})
    .subscribe({
      next: (resp) => {
        ourNotifications.push(resp)
      },
      error: (resp) => {
        console.log(resp)
      },
    })
  const ourSubInitTimeout = misc.sleep(15000) // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541

  // we create a pending post that will fail verification
  const postId1 = uuidv4()
  let variables = {postId: postId1, postType: 'IMAGE'}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId1)
  expect(resp.data.addPost.postStatus).toBe('PENDING')
  let uploadUrl1 = resp.data.addPost.imageUploadUrl
  expect(uploadUrl1).toBeTruthy()

  // we create a pending post that will pass verification
  const postId2 = uuidv4()
  variables = {postId: postId2, postType: 'IMAGE', takenInReal: true}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId2)
  expect(resp.data.addPost.postStatus).toBe('PENDING')
  let uploadUrl2 = resp.data.addPost.imageUploadUrl
  expect(uploadUrl2).toBeTruthy()

  // upload the images, sleep until the posts complete
  await got.put(uploadUrl1, {headers: imageHeaders, body: imageBytes})
  await misc.sleepUntilPostProcessed(ourClient, postId1)

  await got.put(uploadUrl2, {headers: imageHeaders, body: imageBytes})
  await misc.sleepUntilPostProcessed(ourClient, postId2)

  // wait a bit more for messages to show up
  await misc.sleep(5000)

  // check we have received the notifications we expect, in order
  expect(ourNotifications).toHaveLength(2)
  expect(ourNotifications[0].data.onPostNotification).toEqual({
    __typename: 'PostNotification',
    userId: ourUserId,
    type: 'COMPLETED',
    post: {
      __typename: 'Post',
      postId: postId1,
      postStatus: 'COMPLETED',
      isVerified: false,
    },
  })
  expect(ourNotifications[1].data.onPostNotification).toEqual({
    __typename: 'PostNotification',
    userId: ourUserId,
    type: 'COMPLETED',
    post: {
      __typename: 'Post',
      postId: postId2,
      postStatus: 'COMPLETED',
      isVerified: true,
    },
  })

  // shut down the subscription
  ourSub.unsubscribe()
  await ourSubInitTimeout
})
