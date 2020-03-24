/* eslint-env jest */

const fs = require('fs')
const path = require('path')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const schema = require('../../utils/schema.js')

const grantData = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg'))
const grantDataB64 = new Buffer.from(grantData).toString('base64')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Blocked user only see absolutely minimal profile of blocker via direct access', async () => {
  // us and them
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we block them
  let resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(theirUserId)

  // we add a media post, complete it
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let variables = {postId, mediaId, imageData: grantDataB64}
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['addPost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaStatus']).toBe('UPLOADED')
  await misc.sleepUntilPostCompleted(ourClient, postId)

  // we set some details on our profile
  resp = await ourClient.mutate({mutation: schema.setUserDetails, variables: {
    photoPostId: postId,
    bio: 'testing',
    fullName: 'test test',
  }})
  expect(resp['errors']).toBeUndefined()
  resp = await ourClient.mutate({mutation: schema.setUserAcceptedEULAVersion, variables: {version: 'v2020-01-01.1'}})
  expect(resp['errors']).toBeUndefined()

  // retrieve our user object
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  const ourUserFull = resp['data']['self']
  expect(ourUserFull['userId']).toBe(ourUserId)
  expect(ourUserFull['username']).not.toBeNull()
  expect(ourUserFull['acceptedEULAVersion']).not.toBeNull()
  expect(ourUserFull['albumCount']).toBe(0)
  expect(ourUserFull['albums']['items']).toHaveLength(0)
  expect(ourUserFull['anonymouslyLikedPosts']['items']).toHaveLength(0)
  expect(ourUserFull['bio']).not.toBeNull()
  expect(ourUserFull['blockedStatus']).toBe('SELF')
  expect(ourUserFull['blockerStatus']).toBe('SELF')
  expect(ourUserFull['blockedUsers']['items']).toHaveLength(1)
  expect(ourUserFull['chatCount']).toBe(0)
  expect(ourUserFull['chats']['items']).toHaveLength(0)
  expect(ourUserFull['commentsDisabled']).toBe(false)
  expect(ourUserFull['directChat']).toBeNull()
  expect(ourUserFull['email']).not.toBeNull()
  expect(ourUserFull['feed']['items']).toHaveLength(1)
  expect(ourUserFull['followCountsHidden']).toBe(false)
  expect(ourUserFull['followerCount']).toBe(0)
  expect(ourUserFull['followedCount']).toBe(0)
  expect(ourUserFull['followerStatus']).toBe('SELF')
  expect(ourUserFull['followedStatus']).toBe('SELF')
  expect(ourUserFull['followerUsers']['items']).toHaveLength(0)
  expect(ourUserFull['followedUsers']['items']).toHaveLength(0)
  expect(ourUserFull['followedUsersWithStories']['items']).toHaveLength(0)
  expect(ourUserFull['fullName']).not.toBeNull()
  expect(ourUserFull['languageCode']).not.toBeNull()
  expect(ourUserFull['likesDisabled']).toBe(false)
  expect(ourUserFull['mediaObjects']['items']).toHaveLength(1)
  expect(ourUserFull['onymouslyLikedPosts']['items']).toHaveLength(0)
  // skip phone number as that is null for anyone other than SELF, and that's tested elsewhere
  // expect(ourUserFull['phoneNumber']).not.toBeNull()
  expect(ourUserFull['photo']).not.toBeNull()
  expect(ourUserFull['postCount']).toBe(1)
  expect(ourUserFull['posts']['items']).toHaveLength(1)
  expect(ourUserFull['postViewedByCount']).toBe(0)
  expect(ourUserFull['privacyStatus']).toBe('PUBLIC')
  expect(ourUserFull['sharingDisabled']).not.toBeNull()
  expect(ourUserFull['signedUpAt']).not.toBeNull()
  expect(ourUserFull['themeCode']).not.toBeNull()
  expect(ourUserFull['verificationHidden']).toBe(false)
  expect(ourUserFull['viewCountsHidden']).toBe(false)

  // verify they see only a absolutely minimal profile of us
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  const ourUserLimited = resp['data']['user']
  expect(ourUserLimited['userId']).toBe(ourUserFull['userId'])
  expect(ourUserLimited['username']).toBe(ourUserFull['username'])
  expect(ourUserLimited['blockerStatus']).toBe('BLOCKING')

  // adjust everything nulled out or changed, then compare
  ourUserFull['acceptedEULAVersion'] = null
  ourUserFull['albumCount'] = null
  ourUserFull['albums'] = null
  ourUserFull['anonymouslyLikedPosts'] = null
  ourUserFull['bio'] = null
  ourUserFull['blockerStatus'] = 'BLOCKING'
  ourUserFull['blockedStatus'] = 'NOT_BLOCKING'
  ourUserFull['blockedUsers'] = null
  ourUserFull['chatCount'] = null
  ourUserFull['chats'] = null
  ourUserFull['commentsDisabled'] = null
  ourUserFull['email'] = null
  ourUserFull['feed'] = null
  ourUserFull['followCountsHidden'] = null
  ourUserFull['followedCount'] = null
  ourUserFull['followerCount'] = null
  ourUserFull['followedStatus'] = 'NOT_FOLLOWING'
  ourUserFull['followerStatus'] = 'NOT_FOLLOWING'
  ourUserFull['followedUsers'] = null
  ourUserFull['followerUsers'] = null
  ourUserFull['followedUsersWithStories'] = null
  ourUserFull['fullName'] = null
  ourUserFull['languageCode'] = null
  ourUserFull['likesDisabled'] = null
  ourUserFull['mediaObjects'] = null
  ourUserFull['onymouslyLikedPosts'] = null
  // ourUserFull['phoneNumber'] is already null
  ourUserFull['photo'] = null
  ourUserFull['postCount'] = null
  ourUserFull['posts'] = null
  ourUserFull['postViewedByCount'] = null
  ourUserFull['privacyStatus'] = null
  ourUserFull['sharingDisabled'] = null
  ourUserFull['signedUpAt'] = null
  ourUserFull['stories'] = null
  ourUserFull['themeCode'] = null
  ourUserFull['verificationHidden'] = null
  ourUserFull['viewCountsHidden'] = null
  expect(ourUserFull).toEqual(ourUserLimited)
})


test('Blocked cannot see blocker in search results, blocker can see blocked in search results', async () => {
  // use and them
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // change our username to something without a dash https://github.com/Imcloug/Selfly-BackEnd/issues/48
  const ourUsername = 'TESTER' + misc.shortRandomString()
  await ourClient.mutate({mutation: schema.setUsername, variables: {username: ourUsername}})

  // change their username to something without a dash https://github.com/Imcloug/Selfly-BackEnd/issues/48
  const theirUsername = 'TESTER' + misc.shortRandomString()
  await theirClient.mutate({mutation: schema.setUsername, variables: {username: theirUsername}})

  // give the search index a good chunk of time to update
  await misc.sleep(3000)

  // verify they show up in our search results
  let resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: theirUsername}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(1)
  expect(resp['data']['searchUsers']['items'][0]['userId']).toBe(theirUserId)

  // verify we show up in their search results
  resp = await theirClient.query({query: schema.searchUsers, variables: {searchToken: ourUsername}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(1)
  expect(resp['data']['searchUsers']['items'][0]['userId']).toBe(ourUserId)

  // we block them
  resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(theirUserId)

  // verify they still show up in our search results
  resp = await ourClient.query({query: schema.searchUsers, variables: {searchToken: theirUsername}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(1)
  expect(resp['data']['searchUsers']['items'][0]['userId']).toBe(theirUserId)

  // verify we do not show up in their search results
  resp = await theirClient.query({query: schema.searchUsers, variables: {searchToken: ourUsername}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['searchUsers']['items']).toHaveLength(0)
})


test('Blocked cannot see blockers follower or followed users lists', async () => {
  // use and them
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we block them
  let resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(theirUserId)

  // verify they cannot see our list of followers or followed
  resp = await theirClient.query({query: schema.followedUsers, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['followedUsers']).toBeNull()
  resp = await theirClient.query({query: schema.followerUsers, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['followerUsers']).toBeNull()

  // verify we can still see their list of followers or followed
  resp = await ourClient.query({query: schema.followedUsers, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  resp = await ourClient.query({query: schema.followerUsers, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
})


test('Blocked cannot see blockers posts, mediaObjects or stories', async () => {
  // use and them
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we block them
  let resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(theirUserId)

  // verify they cannot see our posts, mediaObjects or stories
  resp = await theirClient.query({query: schema.userStories, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']).toBeNull()
  resp = await theirClient.query({query: schema.userPosts, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']).toBeNull()
  resp = await theirClient.query({query: schema.userMediaObjects, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']).toBeNull()

  // verify we can see their posts, mediaObjects or stories
  resp = await theirClient.query({query: schema.userStories, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['stories']['items']).toHaveLength(0)
  resp = await theirClient.query({query: schema.userPosts, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toHaveLength(0)
  resp = await theirClient.query({query: schema.userMediaObjects, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toHaveLength(0)
})


test('Blocked cannot see blockers lists of likes', async () => {
  // use and them
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we block them
  let resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(theirUserId)

  // verify they cannot see our lists of likes
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['onymouslyLikedPosts']).toBeNull()
  expect(resp['data']['user']['anonymouslyLikedPosts']).toBeNull()

  // verify we can see their list of onymous likes
  resp = await ourClient.query({query: schema.user, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['onymouslyLikedPosts']['items']).toHaveLength(0)
  expect(resp['data']['user']['anonymouslyLikedPosts']).toBeNull()
})


test('Blocked cannot see directly see blockers posts', async () => {
  // use and them
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we block them
  let resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(theirUserId)

  // we add a media post, complete it
  const [postId1, mediaId1] = [uuidv4(), uuidv4()]
  let variables = {postId: postId1, mediaId: mediaId1, imageData: grantDataB64}
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')

  // they add a media post, complete it
  const [postId2, mediaId2] = [uuidv4(), uuidv4()]
  variables = {postId: postId2, mediaId: mediaId2, imageData: grantDataB64}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')

  // verify they cannot see our post or likers of the post
  resp = await theirClient.query({query: schema.post, variables: {postId: postId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']).toBeNull()

  // verify we can see their post and likers of the post
  resp = await ourClient.query({query: schema.post, variables: {postId: postId2}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId2)
})
