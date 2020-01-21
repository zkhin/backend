/* eslint-env jest */

const path = require('path')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const schema = require('../../utils/schema.js')

const grantPath = path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg')
const grantContentType = 'image/jpeg'

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
  const mediaType = 'IMAGE'
  let [postId1, mediaId1] = [uuidv4(), uuidv4()]
  resp = await ourClient.mutate({
    mutation: schema.addOneMediaPost,
    variables: {postId: postId1, mediaId: mediaId1, mediaType},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId1)
  let uploadUrl = resp['data']['addPost']['mediaObjects'][0]['uploadUrl']
  await misc.uploadMedia(grantPath, grantContentType, uploadUrl)
  await misc.sleep(2000)

  // we set our profile photo
  resp = await ourClient.mutate({mutation: schema.setUserDetails, variables: {photoMediaId: mediaId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['photoUrl']).toBeTruthy()

  // they add a media post, complete it
  let [postId2, mediaId2] = [uuidv4(), uuidv4()]
  resp = await theirClient.mutate({
    mutation: schema.addOneMediaPost,
    variables: {postId: postId2, mediaId: mediaId2, mediaType},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId2)
  uploadUrl = resp['data']['addPost']['mediaObjects'][0]['uploadUrl']
  await misc.uploadMedia(grantPath, grantContentType, uploadUrl)
  await misc.sleep(2000)

  // they set their profile photo
  resp = await theirClient.mutate({mutation: schema.setUserDetails, variables: {photoMediaId: mediaId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['photoUrl']).toBeTruthy()

  // retrieve their full user object
  resp = await theirClient.query({query: schema.user, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['userId']).toBe(theirUserId)
  const theirUser = resp['data']['user']

  // verify we can see their profile as normal
  resp = await ourClient.query({query: schema.user, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['userId']).toBe(theirUser['userId'])
  expect(resp['data']['user']['username']).toBe(theirUser['username'])
  expect(resp['data']['user']['fullName']).toBe(theirUser['fullName'])
  expect(resp['data']['user']['bio']).toBe(theirUser['bio'])
  expect(resp['data']['user']['privacyStatus']).toBe(theirUser['privacyStatus'])
  expect(resp['data']['user']['email']).toBeNull()
  expect(resp['data']['user']['phoneNumber']).toBeNull()
  expect(resp['data']['user']['languageCode']).toBeNull()
  expect(resp['data']['user']['postCount']).toBe(theirUser['postCount'])
  expect(resp['data']['user']['likesDisabled']).toBeNull()
  expect(resp['data']['user']['commentsDisabled']).toBeNull()
  expect(resp['data']['user']['verificationHidden']).toBeNull()
  expect(resp['data']['user']['followCountsHidden']).toBeNull()
  expect(resp['data']['user']['followedCount']).toBe(theirUser['followedCount'])
  expect(resp['data']['user']['followerCount']).toBe(theirUser['followerCount'])
  expect(resp['data']['user']['themeCode']).toBe(theirUser['themeCode'])
  expect(resp['data']['user']['photoUrl']).toBeTruthy()
  expect(resp['data']['user']['blockedAt']).toBeTruthy()
  expect(resp['data']['user']['blockerAt']).toBeNull()

  // retrieve our user object
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['userId']).toBe(ourUserId)
  const ourUser = resp['data']['self']

  // verify they see only a absolutely minimal profile of us
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['userId']).toBe(ourUser['userId'])
  expect(resp['data']['user']['username']).toBe(ourUser['username'])
  expect(resp['data']['user']['blockedAt']).toBeNull()
  expect(resp['data']['user']['blockerAt']).toBeTruthy()
  // everything below is nulled out
  expect(resp['data']['user']['privacyStatus']).toBeNull()
  expect(resp['data']['user']['followCountsHidden']).toBeNull()
  expect(resp['data']['user']['fullName']).toBeNull()
  expect(resp['data']['user']['bio']).toBeNull()
  expect(resp['data']['user']['email']).toBeNull()
  expect(resp['data']['user']['phoneNumber']).toBeNull()
  expect(resp['data']['user']['languageCode']).toBeNull()
  expect(resp['data']['user']['postCount']).toBe(0)
  expect(resp['data']['user']['followedCount']).toBe(0)
  expect(resp['data']['user']['followerCount']).toBe(0)
  expect(resp['data']['user']['themeCode']).toBe('black.white')  // the default
  expect(resp['data']['user']['photoUrl']).toBeNull()
})


test('Blocked cannot see blocker in list that have onymously liked a post, blocker can see blocked', async () => {
  // us and them and other
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()
  const [otherClient] = await loginCache.getCleanLogin()

  // other adds a post
  let postId = uuidv4()
  let resp = await otherClient.mutate({mutation: schema.addTextOnlyPost, variables: {postId, text: 'lore ipsum'}})
  expect(resp['errors']).toBeUndefined()

  // we both like it onymously
  resp = await ourClient.mutate({mutation: schema.onymouslyLikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  misc.sleep(1000)  // make sure ordering is correct
  resp = await theirClient.mutate({mutation: schema.onymouslyLikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()

  // we block them
  resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(theirUserId)

  // verify they do not see us in the list of likers of the post
  resp = await theirClient.query({query: schema.getPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getPost']['onymouslyLikedBy']['items']).toHaveLength(1)
  expect(resp['data']['getPost']['onymouslyLikedBy']['items'][0]['userId']).toBe(theirUserId)

  // verify we see them in the list of likers of the post
  resp = await ourClient.query({query: schema.getPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getPost']['onymouslyLikedBy']['items']).toHaveLength(2)
  expect(resp['data']['getPost']['onymouslyLikedBy']['items'][0]['userId']).toBe(ourUserId)
  expect(resp['data']['getPost']['onymouslyLikedBy']['items'][1]['userId']).toBe(theirUserId)
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
  resp = await theirClient.query({query: schema.getStories, variables: {userId: ourUserId}})
  expect(resp['errors'].length).toBeTruthy()
  expect(resp['data']).toBeNull()
  resp = await theirClient.query({query: schema.getPosts, variables: {userId: ourUserId}})
  expect(resp['errors'].length).toBeTruthy()
  expect(resp['data']).toBeNull()
  resp = await theirClient.query({query: schema.getMediaObjects, variables: {userId: ourUserId}})
  expect(resp['errors'].length).toBeTruthy()
  expect(resp['data']).toBeNull()

  // verify we can see their posts, mediaObjects or stories
  resp = await theirClient.query({query: schema.getStories, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  resp = await theirClient.query({query: schema.getPosts, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  resp = await theirClient.query({query: schema.getMediaObjects, variables: {userId: theirUserId}})
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


test('Blocked cannot see directly see blockers posts or list of likers of posts', async () => {
  // use and them
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we block them
  let resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(theirUserId)

  // we add a media post, complete it
  const mediaType = 'IMAGE'
  let [postId1, mediaId1] = [uuidv4(), uuidv4()]
  resp = await ourClient.mutate({
    mutation: schema.addOneMediaPost,
    variables: {postId: postId1, mediaId: mediaId1, mediaType},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId1)
  let uploadUrl = resp['data']['addPost']['mediaObjects'][0]['uploadUrl']
  await misc.uploadMedia(grantPath, grantContentType, uploadUrl)
  await misc.sleep(2000)

  // they add a media post, complete it
  let [postId2, mediaId2] = [uuidv4(), uuidv4()]
  resp = await theirClient.mutate({
    mutation: schema.addOneMediaPost,
    variables: {postId: postId2, mediaId: mediaId2, mediaType},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId2)
  uploadUrl = resp['data']['addPost']['mediaObjects'][0]['uploadUrl']
  await misc.uploadMedia(grantPath, grantContentType, uploadUrl)
  await misc.sleep(2000)

  // verify they cannot see our post or likers of the post
  resp = await theirClient.query({query: schema.getPost, variables: {postId: postId1}})
  expect(resp['errors'].length).toBeTruthy()
  expect(resp['data']['getPost']).toBeNull()

  // verify we can see their post and likers of the post
  resp = await ourClient.query({query: schema.getPost, variables: {postId: postId2}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getPost']['onymouslyLikedBy']['items']).toHaveLength(0)
})
