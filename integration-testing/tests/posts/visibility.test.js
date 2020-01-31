/* eslint-env jest */

const path = require('path')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const schema = require('../../utils/schema.js')

const contentType = 'image/jpeg'
const filePath = path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Visiblity of post(), user.posts(), user.mediaObjects() for a public user', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // a user that follows us
  const [followerClient] = await loginCache.getCleanLogin()
  let resp = await followerClient.mutate({mutation: schema.followUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')

  // some rando off the internet
  const [randoClient] = await loginCache.getCleanLogin()

  // we add a media post, give s3 trigger a second to fire
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  resp = await ourClient.mutate({mutation: schema.addOneMediaPost, variables: {postId, mediaId, mediaType: 'IMAGE'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId)
  const uploadUrl = resp['data']['addPost']['mediaObjects'][0]['uploadUrl']

  // test we can see the uploadUrl if we ask for the incomplete mediaObjects directly
  resp = await ourClient.query({
    query: schema.userMediaObjects,
    variables: {userId: ourUserId, mediaStatus: 'AWAITING_UPLOAD'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toHaveLength(1)
  expect(resp['data']['user']['mediaObjects']['items'][0]['mediaId']).toBe(mediaId)
  expect(resp['data']['user']['mediaObjects']['items'][0]['mediaStatus']).toBe('AWAITING_UPLOAD')
  expect(resp['data']['user']['mediaObjects']['items'][0]['uploadUrl']).not.toBeNull()

  // upload the media, give S3 trigger a second to fire
  await misc.uploadMedia(filePath, contentType, uploadUrl)
  await misc.sleepUntilPostCompleted(ourClient, postId)

  // we should see the post
  resp = await ourClient.query({query: schema.userPosts, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toEqual([expect.objectContaining({postId})])
  resp = await ourClient.query({query: schema.userPosts, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toEqual([expect.objectContaining({postId})])
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']).toMatchObject({postId})

  // we should see the media object
  resp = await ourClient.query({query: schema.userMediaObjects, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toEqual([expect.objectContaining({mediaId})])

  // our follower should be able to see the post
  resp = await followerClient.query({query: schema.userPosts, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toEqual([expect.objectContaining({postId})])
  resp = await followerClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']).toMatchObject({postId})

  // our follower should be able to see the media
  resp = await followerClient.query({query: schema.userMediaObjects, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toEqual([expect.objectContaining({mediaId})])

  // the rando off the internet should be able to see the post
  resp = await randoClient.query({query: schema.userPosts, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toEqual([expect.objectContaining({postId})])
  resp = await randoClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']).toMatchObject({postId})

  // the rando off the internet should be able to see the media object
  resp = await randoClient.query({query: schema.userMediaObjects, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toEqual([expect.objectContaining({mediaId})])
})


test('Visiblity of post(), user.posts(), user.mediaObjects() for a private user', async () => {
  // our user, set to private
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  let resp = await ourClient.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['privacyStatus']).toBe('PRIVATE')

  // some rando off the internet
  const [randoClient] = await loginCache.getCleanLogin()

  // we add a media post, give s3 trigger a second to fire
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  resp = await ourClient.mutate({mutation: schema.addOneMediaPost, variables: {postId, mediaId, mediaType: 'IMAGE'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId)
  const uploadUrl = resp['data']['addPost']['mediaObjects'][0]['uploadUrl']
  await misc.uploadMedia(filePath, contentType, uploadUrl)
  await misc.sleepUntilPostCompleted(ourClient, postId)

  // we should see the post
  resp = await ourClient.query({query: schema.userPosts, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toEqual([expect.objectContaining({postId})])
  resp = await ourClient.query({query: schema.userPosts, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toEqual([expect.objectContaining({postId})])
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']).toMatchObject({postId})

  // we should see the media object
  resp = await ourClient.query({query: schema.userMediaObjects, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toEqual([expect.objectContaining({mediaId})])

  // the rando off the internet should *not* be able to see the post
  resp = await randoClient.query({query: schema.userPosts, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']).toBeNull()
  resp = await randoClient.query({query: schema.post, variables: {postId}})
  expect(resp['data']['post']).toBeNull()

  // the rando off the internet should *not* be able to see the media object
  resp = await randoClient.query({query: schema.userMediaObjects, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']).toBeNull()
})


test('Visiblity of post(), user.posts(), user.mediaObjects() for the follow stages user', async () => {
  // our user, set to private
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  let resp = await ourClient.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['privacyStatus']).toBe('PRIVATE')

  // a user will follows us
  const [followerClient, followerUserId] = await loginCache.getCleanLogin()

  // we add a media post, give s3 trigger a second to fire
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  resp = await ourClient.mutate({mutation: schema.addOneMediaPost, variables: {postId, mediaId, mediaType: 'IMAGE'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId)
  const uploadUrl = resp['data']['addPost']['mediaObjects'][0]['uploadUrl']
  await misc.uploadMedia(filePath, contentType, uploadUrl)
  await misc.sleepUntilPostCompleted(ourClient, postId)

  // request to follow, should *not* be able to see post or mediaObject
  resp = await followerClient.mutate({mutation: schema.followUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  resp = await followerClient.query({query: schema.userPosts, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']).toBeNull()
  resp = await followerClient.query({query: schema.post, variables: {postId}})
  expect(resp['data']['post']).toBeNull()
  resp = await followerClient.query({query: schema.userMediaObjects, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']).toBeNull()

  // deny the follow request, should *not* be able to see post or mediaObject
  resp = await ourClient.mutate({mutation: schema.denyFollowerUser, variables: {userId: followerUserId}})
  expect(resp['errors']).toBeUndefined()
  resp = await followerClient.query({query: schema.userPosts, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']).toBeNull()
  resp = await followerClient.query({query: schema.post, variables: {postId}})
  expect(resp['data']['post']).toBeNull()
  resp = await followerClient.query({query: schema.userMediaObjects, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']).toBeNull()

  // accept the follow request, should be able to see post and mediaObject
  resp = await ourClient.mutate({mutation: schema.acceptFollowerUser, variables: {userId: followerUserId}})
  expect(resp['errors']).toBeUndefined()
  resp = await followerClient.query({query: schema.userPosts, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toEqual([expect.objectContaining({postId})])
  resp = await followerClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']).toMatchObject({postId})
  resp = await followerClient.query({query: schema.userMediaObjects, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toEqual([expect.objectContaining({mediaId})])
})


test('Post that does not exist', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  const postId = uuidv4()
  const resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']).toBeNull()
})


test('Post that is not complete', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a media post, we don't complete it
  const postId = uuidv4()
  let variables = {postId, mediaId: uuidv4(), mediaType: 'IMAGE'}
  let resp = await ourClient.mutate({mutation: schema.addOneMediaPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postStatus']).toBe('PENDING')

  // check we can see the post
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['postStatus']).toBe('PENDING')

  // check they cannot see the post
  resp = await theirClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']).toBeNull()
})


test('Deprecated Query.getPost', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // post that does not exist
  let resp = await ourClient.query({query: schema.getPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getPost']).toBeNull()

  // create the post
  resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables: {postId, text: 'lore ipsum'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // get the post
  resp = await ourClient.query({query: schema.getPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getPost']['postId']).toBe(postId)
})


test('Post.viewedBy only visible to post owner', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables: {postId, text: 'lore ipsum'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // verify we can see the viewedBy list (and it's empty)
  resp = await ourClient.query({query: schema.postViewedBy, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['viewedBy']['items']).toHaveLength(0)

  // verify they cannot see the viewedBy list
  resp = await theirClient.query({query: schema.postViewedBy, variables: {postId}})
  expect(resp['errors'].length).toBe(1)
  expect(resp['data']['post']['viewedBy']).toBeNull()

  // they follow us
  resp = await theirClient.mutate({mutation: schema.followUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')

  // verify they cannot see the viewedBy list
  resp = await theirClient.query({query: schema.postViewedBy, variables: {postId}})
  expect(resp['errors'].length).toBe(1)
  expect(resp['data']['post']['viewedBy']).toBeNull()
})
