/* eslint-env jest */

const rp = require('request-promise-native')
const uuidv4 = require('uuid/v4')
// the aws-appsync-subscription-link pacakge expects WebSocket to be globaly defined, like in the browser
global.WebSocket = require('ws')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const { mutations, subscriptions } = require('../../schema')

const imageHeaders = {'Content-Type': 'image/jpeg'}
const imageBytes = misc.generateRandomJpeg(8, 8)
const imageData = new Buffer.from(imageBytes).toString('base64')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Post message triggers cannot be called from external graphql client', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // create an image post in pending state
  const postId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, postType: 'IMAGE'}})
  expect(resp.errors).toBeUndefined()
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
  await expect(ourClient.mutate({mutation: mutations.triggerPostNotification, variables: {input}}))
    .rejects.toThrow(/ClientError: Access denied/)
})


test('Cannot subscribe to other users notifications', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // verify we cannot subscribe to their messages
  // Note: there doesn't seem to be any error thrown at the time of subscription, it's just that
  // the subscription next() method is never triggered
  const notifications = []
  await ourClient
    .subscribe({query: subscriptions.onPostNotification, variables: {userId: theirUserId}})
    .subscribe({next: resp => { notifications.push(resp) }, error: resp => { console.log(resp) }})

  // they create an image post, complete it
  const postId = uuidv4()
  let variables = {postId, imageData, takenInReal: true}
  let resp = await theirClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
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
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // we subscribe to post notifications
  const ourNotifications = []
  const ourSub = await ourClient
    .subscribe({query: subscriptions.onPostNotification, variables: {userId: ourUserId}})
    .subscribe({next: resp => { ourNotifications.push(resp) }, error: resp => { console.log(resp) }})
  const ourSubInitTimeout = misc.sleep(15000)  // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541

  // we create a pending post that will fail verification
  const postId1 = uuidv4()
  let variables = {postId: postId1, postType: 'IMAGE'}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId1)
  expect(resp.data.addPost.postStatus).toBe('PENDING')
  let uploadUrl1 = resp.data.addPost.imageUploadUrl
  expect(uploadUrl1).toBeTruthy()

  // we create a pending post that will pass verification
  const postId2 = uuidv4()
  variables = {postId: postId2, postType: 'IMAGE', takenInReal: true}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId2)
  expect(resp.data.addPost.postStatus).toBe('PENDING')
  let uploadUrl2 = resp.data.addPost.imageUploadUrl
  expect(uploadUrl2).toBeTruthy()

  // upload the images, sleep until the posts complete
  await rp.put({url: uploadUrl1, headers: imageHeaders, body: imageBytes})
  await misc.sleepUntilPostCompleted(ourClient, postId1)

  await rp.put({url: uploadUrl2, headers: imageHeaders, body: imageBytes})
  await misc.sleepUntilPostCompleted(ourClient, postId2)

  // wait a bit more for messages to show up
  await misc.sleep(2000)

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
    }
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
    }
  })

  // shut down the subscription
  ourSub.unsubscribe()
  await ourSubInitTimeout
})
