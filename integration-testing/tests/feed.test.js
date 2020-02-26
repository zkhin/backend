/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../utils/cognito.js')
const misc = require('../utils/misc.js')
const schema = require('../utils/schema.js')

const imageData = misc.generateRandomJpeg(8, 8)
const imageDataB64 = new Buffer.from(imageData).toString('base64')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('When followed user adds/deletes a post, our feed reacts', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we follow them
  let resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')

  // our feed starts empty
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(0)

  // they add two posts, verify they shows up in our feed in order
  const [postId1, mediaId1] = [uuidv4(), uuidv4()]
  const [postId2, mediaId2] = [uuidv4(), uuidv4()]
  const postText1 = 'Im sorry dave'
  const postText2 = 'Im afraid I cant do that'
  let variables = {postId: postId1, mediaId: mediaId1, text: postText1, imageData: imageDataB64}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)
  variables = {postId: postId2, mediaId: mediaId2, text: postText2, imageData: imageDataB64}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  let items = resp['data']['self']['feed']['items']
  expect(items).toHaveLength(2)
  expect(items[0]['postId']).toBe(postId2)
  expect(items[0]['text']).toBe(postText2)
  expect(items[0]['mediaObjects'][0]['mediaId']).toBe(mediaId2)
  expect(items[1]['postId']).toBe(postId1)
  expect(items[1]['text']).toBe(postText1)
  expect(items[1]['mediaObjects'][0]['mediaId']).toBe(mediaId1)

  // they archive a post, verify it disappears from our feed
  resp = await theirClient.mutate({mutation: schema.archivePost, variables: {postId: postId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['archivePost']['postId']).toBe(postId1)
  expect(resp['data']['archivePost']['postStatus']).toBe('ARCHIVED')
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  items = resp['data']['self']['feed']['items']
  expect(items).toHaveLength(1)
  expect(items[0]['postId']).toBe(postId2)
  expect(items[0]['text']).toBe(postText2)
})


test('When we follow/unfollow a user with posts, our feed reacts', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // they add two posts
  const [postId1, mediaId1] = [uuidv4(), uuidv4()]
  const [postId2, mediaId2] = [uuidv4(), uuidv4()]
  const postText1 = 'Im sorry dave'
  const postText2 = 'Im afraid I cant do that'
  let variables = {postId: postId1, mediaId: mediaId1, text: postText1, imageData: imageDataB64}
  let resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)
  variables = {postId: postId2, mediaId: mediaId2, text: postText2, imageData: imageDataB64}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)

  // our feed starts empty
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  let items = resp['data']['self']['feed']['items']
  expect(items).toHaveLength(0)

  // we follow them, and those two posts show up in our feed
  resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus'] == 'FOLLOWING')
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  items = resp['data']['self']['feed']['items']
  expect(items).toHaveLength(2)
  expect(items[0]['postId']).toBe(postId2)
  expect(items[0]['text']).toBe(postText2)
  expect(items[0]['mediaObjects'][0]['mediaId']).toBe(mediaId2)
  expect(items[1]['postId']).toBe(postId1)
  expect(items[1]['text']).toBe(postText1)
  expect(items[1]['mediaObjects'][0]['mediaId']).toBe(mediaId1)

  // we unfollow them, and those two posts disappear from our feed
  resp = await ourClient.mutate({mutation: schema.unfollowUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['unfollowUser']['followedStatus'] == 'NOT_FOLLOWING')
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  items = resp['data']['self']['feed']['items']
  expect(items).toHaveLength(0)
})


test('When a private user accepts or denies our follow request, our feed reacts', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // set them to private
  let resp = await theirClient.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['privacyStatus']).toBe('PRIVATE')

  // they add two posts
  const [postId1, mediaId1] = [uuidv4(), uuidv4()]
  const [postId2, mediaId2] = [uuidv4(), uuidv4()]
  const postText1 = 'Im sorry dave'
  const postText2 = 'Im afraid I cant do that'
  let variables = {postId: postId1, mediaId: mediaId1, text: postText1, imageData: imageDataB64}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)
  variables = {postId: postId2, mediaId: mediaId2, text: postText2, imageData: imageDataB64}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)

  // our feed starts empty
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(0)

  // we request to follow them, our feed does not react
  resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus'] == 'REQUESTED')
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(0)

  // they accept our follow request, and those two posts show up in our feed
  resp = await theirClient.mutate({mutation: schema.acceptFollowerUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['acceptFollowerUser']['followerStatus'] == 'FOLLOWING')
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  const items = resp['data']['self']['feed']['items']
  expect(items).toHaveLength(2)
  expect(items[0]['postId']).toBe(postId2)
  expect(items[0]['text']).toBe(postText2)
  expect(items[0]['mediaObjects'][0]['mediaId']).toBe(mediaId2)
  expect(items[1]['postId']).toBe(postId1)
  expect(items[1]['text']).toBe(postText1)
  expect(items[1]['mediaObjects'][0]['mediaId']).toBe(mediaId1)

  // they change their mind and deny the request, and those two posts disapear from our feed
  resp = await theirClient.mutate({mutation: schema.denyFollowerUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['denyFollowerUser']['followerStatus'] == 'DENIED')
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(0)
})


test('When a user changes PRIVATE to PUBLIC, and we had an REQUESTED follow request, our feed reacts', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // set them to private
  let resp = await theirClient.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['privacyStatus']).toBe('PRIVATE')

  // they add two posts
  const [postId1, mediaId1] = [uuidv4(), uuidv4()]
  const [postId2, mediaId2] = [uuidv4(), uuidv4()]
  const postText1 = 'Im sorry dave'
  const postText2 = 'Im afraid I cant do that'
  let variables = {postId: postId1, mediaId: mediaId1, text: postText1, imageData: imageDataB64}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)
  variables = {postId: postId2, mediaId: mediaId2, text: postText2, imageData: imageDataB64}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)

  // our feed starts empty
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(0)

  // we request to follow them, our feed does not react
  resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus'] == 'REQUESTED')
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(0)

  // they change from private to public
  resp = await theirClient.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PUBLIC'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['privacyStatus']).toBe('PUBLIC')

  // our follow request should have gone though, so their two posts should now be in our feed
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  const items = resp['data']['self']['feed']['items']
  expect(items).toHaveLength(2)
  expect(items[0]['postId']).toBe(postId2)
  expect(items[0]['text']).toBe(postText2)
  expect(items[0]['mediaObjects'][0]['mediaId']).toBe(mediaId2)
  expect(items[1]['postId']).toBe(postId1)
  expect(items[1]['text']).toBe(postText1)
  expect(items[1]['mediaObjects'][0]['mediaId']).toBe(mediaId1)
})


// waiting on a way to externally trigger the 'archive expired posts' cron job
test.skip('Post that expires is removed from feed', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we follow them
  let resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus'] == 'FOLLOWING')

  // they add a post that expires in a millisecond
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let variables = {postId, mediaId, lifetime: 'PT0.001S', imageData: imageDataB64}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // since cron job hasn't yet run, that post should be in our feed
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(1)
  expect(resp['data']['self']['feed']['items'][0]['postId']).toBe(postId)

  // TODO trigger the cron job

  // that post should now have disappeared from our feed
  //resp = await ourClient.query({query: schema.selfFeed})
  //expect(resp['data']['self']['feed']['items']).toHaveLength(0)

})


test('Feed Post.postedBy.blockerStatus and followedStatus are filled in correctly', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we follow them
  let resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')

  // they add a post
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  resp = await theirClient.mutate({mutation: schema.addPost, variables: {postId, mediaId, imageData: imageDataB64}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // see how that looks in our feed
  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(1)
  expect(resp['data']['self']['feed']['items'][0]['postId']).toBe(postId)
  expect(resp['data']['self']['feed']['items'][0]['postedBy']['userId']).toBe(theirUserId)
  expect(resp['data']['self']['feed']['items'][0]['postedBy']['blockerStatus']).toBe('NOT_BLOCKING')
  expect(resp['data']['self']['feed']['items'][0]['postedBy']['followedStatus']).toBe('FOLLOWING')

  // see how that looks in their feed
  resp = await theirClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(1)
  expect(resp['data']['self']['feed']['items'][0]['postId']).toBe(postId)
  expect(resp['data']['self']['feed']['items'][0]['postedBy']['userId']).toBe(theirUserId)
  expect(resp['data']['self']['feed']['items'][0]['postedBy']['blockerStatus']).toBe('SELF')
  expect(resp['data']['self']['feed']['items'][0]['postedBy']['followedStatus']).toBe('SELF')
})


test('Feed privacy', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // verify we can see our feed, via self and user queries
  let resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(0)
  resp = await ourClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['feed']['items']).toHaveLength(0)

  // verify they can *not* see our feed
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['feed']).toBeNull()
})
