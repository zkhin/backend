const fs = require('fs')
const path = require('path')
const {v4: uuidv4} = require('uuid')

const {cognito, eventually, shortRandomString} = require('../../utils')
const {mutations, queries} = require('../../schema')

const grantData = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg'))
const grantDataB64 = new Buffer.from(grantData).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Blocked user only see absolutely minimal profile of blocker via direct access', async () => {
  // us and them
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // we block them
  let resp = await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: theirUserId}})
  expect(resp.data.blockUser.userId).toBe(theirUserId)

  // we add an image post
  const postId = uuidv4()
  let variables = {postId, imageData: grantDataB64, takenInReal: true}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // we set some details on our profile
  await ourClient
    .mutate({
      mutation: mutations.setUserDetails,
      variables: {
        photoPostId: postId,
        bio: 'testing',
        fullName: 'test test',
        dateOfBirth: '2020-01-09',
        gender: 'FEMALE',
      },
    })
    .then(({data: {setUserDetails: user}}) => expect(user.userId).toBe(ourUserId))
  await ourClient
    .mutate({mutation: mutations.setThemeCode, variables: {themeCode: 'black.green'}})
    .then(({data: {setThemeCode: user}}) => expect(user.themeCode).toBe('black.green'))
  await ourClient
    .mutate({mutation: mutations.setUserAcceptedEULAVersion, variables: {version: 'v2020-01-01.1'}})
    .then(({data: {setUserAcceptedEULAVersion: user}}) => expect(user.acceptedEULAVersion).toBe('v2020-01-01.1'))

  // retrieve our user object
  const ourUserFull = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.username).toBeTruthy()
    expect(data.self.acceptedEULAVersion).toBeTruthy()
    expect(data.self.adsDisabled).toBe(false)
    expect(data.self.albumCount).toBe(0)
    expect(data.self.albums.items).toHaveLength(0)
    expect(data.self.anonymouslyLikedPosts.items).toHaveLength(0)
    expect(data.self.bio).toBeTruthy()
    expect(data.self.blockedStatus).toBe('SELF')
    expect(data.self.blockerStatus).toBe('SELF')
    expect(data.self.blockedUsers.items).toHaveLength(1)
    expect(data.self.cardCount).toBe(0)
    expect(data.self.cards.items).toHaveLength(0)
    expect(data.self.chatCount).toBe(0)
    expect(data.self.chats.items).toHaveLength(0)
    expect(data.self.chatsWithUnviewedMessagesCount).toBe(0)
    expect(data.self.commentsDisabled).toBe(false)
    expect(data.self.dateOfBirth).toBe('2020-01-09')
    expect(data.self.datingStatus).toBe('DISABLED')
    expect(data.self.directChat).toBeNull()
    expect(data.self.email).toBeTruthy()
    expect(data.self.feed.items).toHaveLength(1)
    expect(data.self.followCountsHidden).toBe(false)
    expect(data.self.followersCount).toBe(0)
    expect(data.self.followersRequestedCount).toBe(0)
    expect(data.self.followedsCount).toBe(0)
    expect(data.self.followerStatus).toBe('SELF')
    expect(data.self.followedStatus).toBe('SELF')
    expect(data.self.followerUsers.items).toHaveLength(0)
    expect(data.self.followedUsers.items).toHaveLength(0)
    expect(data.self.followedUsersWithStories.items).toHaveLength(0)
    expect(data.self.fullName).toBeTruthy()
    expect(data.self.gender).toBe('FEMALE')
    expect(data.self.languageCode).toBeTruthy()
    expect(data.self.likesDisabled).toBe(false)
    expect(data.self.onymouslyLikedPosts.items).toHaveLength(0)
    // skip phone number as that is null for anyone other than SELF, and that's tested elsewhere
    // expect(data.self.phoneNumber).toBeTruthy()
    expect(data.self.photo).toBeTruthy()
    expect(data.self.postCount).toBe(1)
    expect(data.self.posts.items).toHaveLength(1)
    expect(data.self.postsWithUnviewedComments.items).toHaveLength(0)
    expect(data.self.postViewedByCount).toBe(0)
    expect(data.self.privacyStatus).toBe('PUBLIC')
    expect(data.self.sharingDisabled).toBe(false)
    expect(data.self.signedUpAt).toBeTruthy()
    expect(data.self.subscriptionLevel).toBe('BASIC')
    expect(data.self.subscriptionExpiresAt).toBeNull()
    expect(data.self.themeCode).toBeTruthy()
    expect(data.self.userStatus).toBe('ACTIVE')
    expect(data.self.verificationHidden).toBe(false)
    expect(data.self.viewCountsHidden).toBe(false)
    return data.self
  })

  // verify they see only a absolutely minimal profile of us
  const ourUserLimited = await eventually(async () => {
    const {data} = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
    expect(data.user.userId).toBe(ourUserFull.userId)
    expect(data.user.username).toBe(ourUserFull.username)
    expect(data.user.blockerStatus).toBe('BLOCKING')
    return data.user
  })

  // adjust everything nulled out or changed, then compare
  ourUserFull.acceptedEULAVersion = null
  ourUserFull.adsDisabled = null
  ourUserFull.albumCount = null
  ourUserFull.albums = null
  ourUserFull.anonymouslyLikedPosts = null
  ourUserFull.bio = null
  ourUserFull.blockerStatus = 'BLOCKING'
  ourUserFull.blockedStatus = 'NOT_BLOCKING'
  ourUserFull.blockedUsers = null
  ourUserFull.cardCount = null
  ourUserFull.cards = null
  ourUserFull.chatCount = null
  ourUserFull.chats = null
  ourUserFull.chatsWithUnviewedMessagesCount = null
  ourUserFull.commentsDisabled = null
  ourUserFull.dateOfBirth = null
  ourUserFull.datingStatus = null
  ourUserFull.email = null
  ourUserFull.feed = null
  ourUserFull.followCountsHidden = null
  ourUserFull.followedsCount = null
  ourUserFull.followersCount = null
  ourUserFull.followersRequestedCount = null
  ourUserFull.followedStatus = 'NOT_FOLLOWING'
  ourUserFull.followerStatus = 'NOT_FOLLOWING'
  ourUserFull.followedUsers = null
  ourUserFull.followerUsers = null
  ourUserFull.followedUsersWithStories = null
  ourUserFull.fullName = null
  ourUserFull.gender = null
  ourUserFull.languageCode = null
  ourUserFull.likesDisabled = null
  ourUserFull.onymouslyLikedPosts = null
  // ourUserFull.phoneNumber is already null
  ourUserFull.photo = null
  ourUserFull.postCount = null
  ourUserFull.posts = null
  ourUserFull.postsWithUnviewedComments = null
  ourUserFull.postViewedByCount = null
  ourUserFull.privacyStatus = null
  ourUserFull.sharingDisabled = null
  ourUserFull.signedUpAt = null
  ourUserFull.stories = null
  ourUserFull.subscriptionLevel = null
  ourUserFull.themeCode = null
  ourUserFull.userStatus = null
  ourUserFull.verificationHidden = null
  ourUserFull.viewCountsHidden = null
  expect(ourUserFull).toEqual(ourUserLimited)
})

test('Blocked cannot see blocker in search results, blocker can see blocked in search results', async () => {
  // use and them
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // change our username to something without a dash https://github.com/Imcloug/Selfly-BackEnd/issues/48
  const ourUsername = 'TESTER' + shortRandomString()
  await ourClient.mutate({mutation: mutations.setUsername, variables: {username: ourUsername}})

  // change their username to something without a dash https://github.com/Imcloug/Selfly-BackEnd/issues/48
  const theirUsername = 'TESTER' + shortRandomString()
  await theirClient.mutate({mutation: mutations.setUsername, variables: {username: theirUsername}})

  // verify they show up in our search results
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.searchUsers, variables: {searchToken: theirUsername}})
    expect(data.searchUsers.items).toHaveLength(1)
    expect(data.searchUsers.items[0].userId).toBe(theirUserId)
  })

  // verify we show up in their search results
  let resp = await theirClient.query({query: queries.searchUsers, variables: {searchToken: ourUsername}})
  expect(resp.data.searchUsers.items).toHaveLength(1)
  expect(resp.data.searchUsers.items[0].userId).toBe(ourUserId)

  // we block them
  resp = await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: theirUserId}})
  expect(resp.data.blockUser.userId).toBe(theirUserId)

  // verify they still show up in our search results
  resp = await ourClient.query({query: queries.searchUsers, variables: {searchToken: theirUsername}})
  expect(resp.data.searchUsers.items).toHaveLength(1)
  expect(resp.data.searchUsers.items[0].userId).toBe(theirUserId)

  // verify we do not show up in their search results
  resp = await theirClient.query({query: queries.searchUsers, variables: {searchToken: ourUsername}})
  expect(resp.data.searchUsers.items).toHaveLength(0)
})

test('Blocked cannot see blockers follower or followed users lists', async () => {
  // use and them
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // we block them
  let resp = await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: theirUserId}})
  expect(resp.data.blockUser.userId).toBe(theirUserId)

  // verify they cannot see our list of followers or followed
  resp = await theirClient.query({query: queries.followedUsers, variables: {userId: ourUserId}})
  expect(resp.data.user.followedUsers).toBeNull()
  resp = await theirClient.query({query: queries.followerUsers, variables: {userId: ourUserId}})
  expect(resp.data.user.followerUsers).toBeNull()

  // verify we can still see their list of followers or followed
  resp = await ourClient.query({query: queries.followedUsers, variables: {userId: theirUserId}})
  resp = await ourClient.query({query: queries.followerUsers, variables: {userId: theirUserId}})
})

test('Blocked cannot see blockers posts or stories', async () => {
  // use and them
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // we block them
  let resp = await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: theirUserId}})
  expect(resp.data.blockUser.userId).toBe(theirUserId)

  // verify they cannot see our posts or stories
  resp = await theirClient.query({query: queries.userStories, variables: {userId: ourUserId}})
  expect(resp.data.user.stories).toBeNull()
  resp = await theirClient.query({query: queries.userPosts, variables: {userId: ourUserId}})
  expect(resp.data.user.posts).toBeNull()

  // verify we can see their posts or stories
  resp = await theirClient.query({query: queries.userStories, variables: {userId: theirUserId}})
  expect(resp.data.user.stories.items).toHaveLength(0)
  resp = await theirClient.query({query: queries.userPosts, variables: {userId: theirUserId}})
  expect(resp.data.user.posts.items).toHaveLength(0)
})

test('Blocked cannot see blockers lists of likes', async () => {
  // use and them
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // we block them
  let resp = await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: theirUserId}})
  expect(resp.data.blockUser.userId).toBe(theirUserId)

  // verify they cannot see our lists of likes
  resp = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp.data.user.onymouslyLikedPosts).toBeNull()
  expect(resp.data.user.anonymouslyLikedPosts).toBeNull()

  // verify we can see their list of onymous likes
  resp = await ourClient.query({query: queries.user, variables: {userId: theirUserId}})
  expect(resp.data.user.onymouslyLikedPosts.items).toHaveLength(0)
  expect(resp.data.user.anonymouslyLikedPosts).toBeNull()
})

test('Blocked cannot see directly see blockers posts', async () => {
  // use and them
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // we block them
  let resp = await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: theirUserId}})
  expect(resp.data.blockUser.userId).toBe(theirUserId)

  // we add an image post, complete it
  const postId1 = uuidv4()
  let variables = {postId: postId1, imageData: grantDataB64}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId1)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // they add an image post, complete it
  const postId2 = uuidv4()
  variables = {postId: postId2, imageData: grantDataB64}
  resp = await theirClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId2)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // verify they cannot see our post or likers of the post
  resp = await theirClient.query({query: queries.post, variables: {postId: postId1}})
  expect(resp.data.post).toBeNull()

  // verify we can see their post and likers of the post
  resp = await ourClient.query({query: queries.post, variables: {postId: postId2}})
  expect(resp.data.post.postId).toBe(postId2)
})
