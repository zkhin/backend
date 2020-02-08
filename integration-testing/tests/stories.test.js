/* eslint-env jest */

const fs = require('fs')
const path = require('path')
const uuidv4 = require('uuid/v4')
require('isomorphic-fetch')

const cognito = require('../utils/cognito.js')
const misc = require('../utils/misc.js')
const schema = require('../utils/schema.js')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Posts that are not within a day of expiring do not show up as a stories', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we follow them
  let resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus'] == 'FOLLOWING')

  // they add two posts that are not close to expiring
  const [postId1, postId2] = [uuidv4(), uuidv4()]
  resp = await theirClient.mutate({
    mutation: schema.addTextOnlyPost,
    variables: {postId: postId1, text: 'never expires'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)
  resp = await theirClient.mutate({
    mutation: schema.addTextOnlyPost,
    variables: {postId: postId2, text: 'in a week', lifetime: 'P7D'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)

  // verify they still have no stories
  resp = await theirClient.query({query: schema.userStories, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']['items']).toHaveLength(0)
  resp = await ourClient.query({query: schema.userStories, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']['items']).toHaveLength(0)

  // verify we don't see them as having stories
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followedUsersWithStories']['items']).toHaveLength(0)
})


test('Add a post that shows up as story', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we follow them
  let resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus'] == 'FOLLOWING')

  // they add a post that expires in a day
  const postId = uuidv4()
  resp = await theirClient.mutate({
    mutation: schema.addTextOnlyPost,
    variables: {postId, text: 'insta story!', lifetime: 'P1D'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // that post should show up as a story for them
  resp = await ourClient.query({query: schema.userStories, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']['items']).toHaveLength(1)
  expect(resp['data']['user']['stories']['items'][0]['postId']).toBe(postId)

  // they should show up as having a story to us
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followedUsersWithStories']['items']).toHaveLength(1)
  expect(resp['data']['self']['followedUsersWithStories']['items'][0]['userId']).toBe(theirUserId)
  expect(resp['data']['self']['followedUsersWithStories']['items'][0]['blockerStatus']).toBe('NOT_BLOCKING')
  expect(resp['data']['self']['followedUsersWithStories']['items'][0]['followedStatus']).toBe('FOLLOWING')

  // verify they cannot see our followedUsersWithStories
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['followedUsersWithStories']).toBeNull()
})


test('Add posts with media show up in stories', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const contentType = 'image/jpeg'
  const imageData = fs.readFileSync(path.join(__dirname, '..', 'fixtures', 'grant.jpg'))

  // we add a media post, give s3 trigger a second to fire
  const [postId1, mediaId1] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({
    mutation: schema.addOneMediaPost,
    variables: {postId: postId1, mediaId: mediaId1, mediaType: 'IMAGE', lifetime: 'PT1M'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId1)
  const uploadUrl1 = resp['data']['addPost']['mediaObjects'][0]['uploadUrl']
  // upload the media, give S3 trigger a second to fire
  await misc.uploadMedia(imageData, contentType, uploadUrl1)
  await misc.sleepUntilPostCompleted(ourClient, postId1)

  // we add a media post, give s3 trigger a second to fire
  const [postId2, mediaId2] = [uuidv4(), uuidv4()]
  resp = await ourClient.mutate({
    mutation: schema.addOneMediaPost,
    variables: {postId: postId2, mediaId: mediaId2, mediaType: 'IMAGE', lifetime: 'PT2H'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId2)
  const uploadUrl2 = resp['data']['addPost']['mediaObjects'][0]['uploadUrl']
  // upload the media, give S3 trigger a second to fire
  await misc.uploadMedia(imageData, contentType, uploadUrl2)
  await misc.sleepUntilPostCompleted(ourClient, postId2)

  // verify we see those stories, with media
  resp = await ourClient.query({query: schema.userStories, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']['items']).toHaveLength(2)
  expect(resp['data']['user']['stories']['items'][0]['postId']).toBe(postId1)
  expect(resp['data']['user']['stories']['items'][0]['mediaObjects']).toHaveLength(1)
  expect(resp['data']['user']['stories']['items'][0]['mediaObjects'][0]['mediaId']).toBe(mediaId1)
  expect(resp['data']['user']['stories']['items'][0]['mediaObjects'][0]['url']).toBeTruthy()
  expect(resp['data']['user']['stories']['items'][1]['postId']).toBe(postId2)
  expect(resp['data']['user']['stories']['items'][1]['mediaObjects']).toHaveLength(1)
  expect(resp['data']['user']['stories']['items'][1]['mediaObjects'][0]['mediaId']).toBe(mediaId2)
  expect(resp['data']['user']['stories']['items'][1]['mediaObjects'][0]['url']).toBeTruthy()
})


test('Stories are ordered by first-to-expire-first', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // we add three stories with various lifetimes
  const [postId1, postId2, postId3] = [uuidv4(), uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({
    mutation: schema.addTextOnlyPost,
    variables: {postId: postId1, text: '6 hrs', lifetime: 'PT6H'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)
  resp = await ourClient.mutate({
    mutation: schema.addTextOnlyPost,
    variables: {postId: postId2, text: '1 hour', lifetime: 'PT1H'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)
  resp = await ourClient.mutate({
    mutation: schema.addTextOnlyPost,
    variables: {postId: postId3, text: '12 hours', lifetime: 'PT12H'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId3)

  // verify those show up in the right order
  resp = await ourClient.query({query: schema.userStories, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']['items']).toHaveLength(3)
  expect(resp['data']['user']['stories']['items'][0]['postId']).toBe(postId2)
  expect(resp['data']['user']['stories']['items'][1]['postId']).toBe(postId1)
  expect(resp['data']['user']['stories']['items'][2]['postId']).toBe(postId3)
})


test('Followed users with stories are ordered by first-to-expire-first', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [other1Client, other1UserId] = await loginCache.getCleanLogin()
  const [other2Client, other2UserId] = await loginCache.getCleanLogin()

  // we follow the two other users
  let resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: other1UserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')
  resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: other2UserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')

  // they each add a story
  resp = await other1Client.mutate({
    mutation: schema.addTextOnlyPost,
    variables: {postId: uuidv4(), text: '12 hrs', lifetime: 'PT12H'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')
  resp = await other2Client.mutate({
    mutation: schema.addTextOnlyPost,
    variables: {postId: uuidv4(), text: '6 hrs', lifetime: 'PT6H'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')

  // verify those show up in the right order
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followedUsersWithStories']['items']).toHaveLength(2)
  expect(resp['data']['self']['followedUsersWithStories']['items'][0]['userId']).toBe(other2UserId)
  expect(resp['data']['self']['followedUsersWithStories']['items'][1]['userId']).toBe(other1UserId)

  // another story is added that's about to expire
  resp = await other1Client.mutate({
    mutation: schema.addTextOnlyPost,
    variables: {postId: uuidv4(), text: '1 hours', lifetime: 'PT1H'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')

  // verify that reversed the order
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followedUsersWithStories']['items']).toHaveLength(2)
  expect(resp['data']['self']['followedUsersWithStories']['items'][0]['userId']).toBe(other1UserId)
  expect(resp['data']['self']['followedUsersWithStories']['items'][1]['userId']).toBe(other2UserId)

  // another story is added that doesn't change the order
  resp = await other2Client.mutate({
    mutation: schema.addTextOnlyPost,
    variables: {postId: uuidv4(), text: '13 hrs', lifetime: 'PT13H'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')

  // verify order has not changed
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followedUsersWithStories']['items']).toHaveLength(2)
  expect(resp['data']['self']['followedUsersWithStories']['items'][0]['userId']).toBe(other1UserId)
  expect(resp['data']['self']['followedUsersWithStories']['items'][1]['userId']).toBe(other2UserId)
})


test('Stories of private user are visible to themselves and followers only', async () => {
  // us, a private user with a story
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const postId = uuidv4()
  let resp = await ourClient.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['privacyStatus']).toBe('PRIVATE')
  resp = await ourClient.mutate({
    mutation: schema.addTextOnlyPost,
    variables: {postId, text: 'expires in an hour', lifetime: 'PT1H'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // verify we can see our story
  resp = await ourClient.query({query: schema.userStories, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']['items']).toHaveLength(1)
  expect(resp['data']['user']['stories']['items'][0]['postId']).toBe(postId)
  resp = await ourClient.query({query: schema.userStories, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']['items']).toHaveLength(1)
  expect(resp['data']['user']['stories']['items'][0]['postId']).toBe(postId)

  // verify new user, not yet following us, cannot see our stories
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()
  resp = await theirClient.query({query: schema.userStories, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']).toBeNull()

  // they request to follow us, verify still cannot see our stories
  resp = await theirClient.mutate({mutation: schema.followUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('REQUESTED')
  resp = await theirClient.query({query: schema.userStories, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']).toBeNull()

  // we deny their request, verify they cannot see our stories
  resp = await ourClient.mutate({mutation: schema.denyFollowerUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['denyFollowerUser']['followerStatus']).toBe('DENIED')
  resp = await theirClient.query({query: schema.userStories, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']).toBeNull()

  // approve their request, verify they can now see our stories
  resp = await ourClient.mutate({mutation: schema.acceptFollowerUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['acceptFollowerUser']['followerStatus']).toBe('FOLLOWING')
  resp = await theirClient.query({query: schema.userStories, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']['items']).toHaveLength(1)
  expect(resp['data']['user']['stories']['items'][0]['postId']).toBe(postId)

  // they unfollow us, verify they cannot see our stories
  resp = await theirClient.mutate({mutation: schema.unfollowUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['unfollowUser']['followedStatus']).toBe('NOT_FOLLOWING')
  resp = await theirClient.query({query: schema.userStories, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']).toBeNull()
})


// waiting on a way to externally trigger the 'archive expired posts' cron job
test.skip('Post that expires is removed from stories', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we follow them
  let resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus'] == 'FOLLOWING')

  // they add a post that expires in a millisecond
  const postId = uuidv4()
  resp = await theirClient.mutate({
    mutation: schema.addTextOnlyPost,
    variables: {postId, text: 'expires 1ms', lifetime: 'PT0.001S'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // cron job hasn't yet run, so that post should be a story
  resp = await theirClient.query({query: schema.userStories, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']['items']).toHaveLength(1)
  expect(resp['data']['user']['stories']['items'][0]['postId']).toBe(postId)
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followedUsersWithStories']['items']).toHaveLength(1)
  expect(resp['data']['self']['followedUsersWithStories']['items'][0]['userId']).toBe(theirUserId)

  // TODO trigger the cron job

  // that post should now have disappeared from stories
  resp = await theirClient.query({query: schema.userStories, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']['items']).toHaveLength(0)
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followedUsersWithStories']['items']).toHaveLength(0)
})


test('Post that is archived is removed from stories', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we follow them
  let resp = await ourClient.mutate({mutation: schema.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus'] == 'FOLLOWING')

  // they add a post that expires in an hour
  const postId = uuidv4()
  resp = await theirClient.mutate({
    mutation: schema.addTextOnlyPost,
    variables: {postId, text: 'expires in an hour', lifetime: 'PT1H'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)

  // that post should be a story
  resp = await theirClient.query({query: schema.userStories, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']['items']).toHaveLength(1)
  expect(resp['data']['user']['stories']['items'][0]['postId']).toBe(postId)
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followedUsersWithStories']['items']).toHaveLength(1)
  expect(resp['data']['self']['followedUsersWithStories']['items'][0]['userId']).toBe(theirUserId)

  // they archive that post
  resp = await theirClient.mutate({mutation: schema.archivePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['archivePost']['postStatus']).toBe('ARCHIVED')

  // that post should now have disappeared from stories
  resp = await theirClient.query({query: schema.userStories, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']['items']).toHaveLength(0)
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['followedUsersWithStories']['items']).toHaveLength(0)
})
