const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito')
const misc = require('../../utils/misc')
const {mutations, subscriptions} = require('../../schema')

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

test('USER_FOLLOWED_USERS_WITH_STORIES_CHANGED triggers correctly when changing first story', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // we subscribe to notifications
  let notificationsCount = 0
  const notificationHandlers = []
  const notifications = [
    new Promise((resolve, reject) => notificationHandlers.push({resolve, reject})),
    new Promise((resolve, reject) => notificationHandlers.push({resolve, reject})),
    new Promise((resolve, reject) => notificationHandlers.push({resolve, reject})),
    new Promise((resolve, reject) => notificationHandlers.push({resolve, reject})),
  ]
  const sub = await ourClient
    .subscribe({query: subscriptions.onNotification, variables: {userId: ourUserId}})
    .subscribe({
      next: ({data}) => {
        if (data.onNotification.type.startsWith('USER_FOLLOWED_USERS_WITH_STORIES_CHANGED')) {
          notificationsCount += 1
          notificationHandlers.shift().resolve(data.onNotification)
        }
      },
      error: (resp) => notificationHandlers.shift().reject(resp), // necessry? could this just throw an error?
    })
  const subInitTimeout = misc.sleep(15000) // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541
  await misc.sleep(2000) // let the subscription initialize

  // we follow them
  await ourClient
    .mutate({mutation: mutations.followUser, variables: {userId: theirUserId}})
    .then(({data: {followUser: user}}) => expect(user.followedStatus).toBe('FOLLOWING'))

  // they add a story
  const postId1 = uuidv4()
  await theirClient
    .mutate({mutation: mutations.addPost, variables: {postId: postId1, imageData, lifetime: 'P1D'}})
    .then(({data: {addPost: post}}) => expect(post.postStatus).toBe('COMPLETED'))

  // check we received a notification for that new story
  await notifications.shift().then((notif) => {
    expect(notif.followedUserId).toBe(theirUserId)
    expect(notif.postId).toBe(postId1)
    expect((notificationsCount -= 1)).toBe(0)
  })

  // they add another story that expires before the first one
  const postId2 = uuidv4()
  await theirClient
    .mutate({mutation: mutations.addPost, variables: {postId: postId2, imageData, lifetime: 'PT1H'}})
    .then(({data: {addPost: post}}) => expect(post.postStatus).toBe('COMPLETED'))

  // check we received a notification for that story
  await notifications.shift().then((notif) => {
    expect(notif.followedUserId).toBe(theirUserId)
    expect(notif.postId).toBe(postId2)
    expect((notificationsCount -= 1)).toBe(0)
  })

  // they archive their latest story (thus changing what is the first story)
  await theirClient
    .mutate({mutation: mutations.archivePost, variables: {postId: postId2}})
    .then(({data: {archivePost: post}}) => expect(post.postStatus).toBe('ARCHIVED'))

  // check we received a notification for that change in first story
  await notifications.shift().then((notif) => {
    expect(notif.followedUserId).toBe(theirUserId)
    expect(notif.postId).toBe(postId1)
    expect((notificationsCount -= 1)).toBe(0)
  })

  // they delete their remaining story (thus removing out their first story)
  await theirClient
    .mutate({mutation: mutations.deletePost, variables: {postId: postId1}})
    .then(({data: {deletePost: post}}) => expect(post.postStatus).toBe('DELETING'))

  // check we received a notification for that change in first story
  await notifications.shift().then((notif) => {
    expect(notif.followedUserId).toBe(theirUserId)
    expect(notif.postId).toBeNull()
    expect((notificationsCount -= 1)).toBe(0)
  })

  // shut down the subscription
  sub.unsubscribe()
  await subInitTimeout
})
