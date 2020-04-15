/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const { mutations, queries } = require('../../schema')

const imageBytes = misc.generateRandomJpeg(8, 8)
const imageData = new Buffer.from(imageBytes).toString('base64')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Cannot like/dislike posts that do not exist', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  let variables = {postId: uuidv4()}

  await expect(ourClient.mutate({mutation: mutations.onymouslyLikePost, variables})).rejects.toThrow('ClientError')
  await expect(ourClient.mutate({mutation: mutations.anonymouslyLikePost, variables})).rejects.toThrow('ClientError')
  await expect(ourClient.mutate({mutation: mutations.dislikePost, variables})).rejects.toThrow('ClientError')
})


test('Cannot like/dislike PENDING posts', async () => {
  // we add an image post, but don't upload the image
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postStatus']).toBe('PENDING')

  // verify we can't like/dislike the post
  let variables = {postId}
  await expect(ourClient.mutate({mutation: mutations.onymouslyLikePost, variables})).rejects.toThrow('ClientError')
  await expect(ourClient.mutate({mutation: mutations.anonymouslyLikePost, variables})).rejects.toThrow('ClientError')
  await expect(ourClient.mutate({mutation: mutations.dislikePost, variables})).rejects.toThrow('ClientError')
})


test('Cannot like/dislike ARCHIVED posts', async () => {
  // we add a post, and archive it
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  await misc.sleep(1000)  // let dynamo converge
  resp = await ourClient.mutate({mutation: mutations.archivePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['archivePost']['postId']).toBe(postId)
  expect(resp['data']['archivePost']['postStatus']).toBe('ARCHIVED')

  // verify we can't like/dislike the post
  variables = {postId}
  await expect(ourClient.mutate({mutation: mutations.onymouslyLikePost, variables})).rejects.toThrow('ClientError')
  await expect(ourClient.mutate({mutation: mutations.anonymouslyLikePost, variables})).rejects.toThrow('ClientError')
  await expect(ourClient.mutate({mutation: mutations.dislikePost, variables})).rejects.toThrow('ClientError')
})


test('Cannot double like a post', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // add two posts
  const [postId1, postId2] = [uuidv4(), uuidv4()]
  let variables = {postId: postId1, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  variables = {postId: postId2, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()

  // onymously like the first post
  resp = await ourClient.mutate({mutation: mutations.onymouslyLikePost, variables: {postId: postId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['onymouslyLikePost']['postId']).toBe(postId1)
  expect(resp['data']['onymouslyLikePost']['likeStatus']).toBe('ONYMOUSLY_LIKED')

  // anonymously like the second post
  resp = await ourClient.mutate({mutation: mutations.anonymouslyLikePost, variables: {postId: postId2}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['anonymouslyLikePost']['postId']).toBe(postId2)
  expect(resp['data']['anonymouslyLikePost']['likeStatus']).toBe('ANONYMOUSLY_LIKED')

  // verify we can't re-like the first post
  await expect(ourClient.mutate({
    mutation: mutations.onymouslyLikePost,
    variables: {postId: postId1},
  })).rejects.toThrow('ClientError')
  await expect(ourClient.mutate({
    mutation: mutations.anonymouslyLikePost,
    variables: {postId: postId1},
  })).rejects.toThrow('ClientError')

  // verify we can't re-like the second post
  await expect(ourClient.mutate({
    mutation: mutations.onymouslyLikePost,
    variables: {postId: postId2},
  })).rejects.toThrow('ClientError')
  await expect(ourClient.mutate({
    mutation: mutations.anonymouslyLikePost,
    variables: {postId: postId2}
  })).rejects.toThrow('ClientError')
})


test('Cannot dislike a post we have not liked', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()

  // verify we can't dislike it, since we haven't already liked it
  await expect(ourClient.mutate({mutation: mutations.dislikePost, variables: {postId}}))
    .rejects.toThrow('ClientError')
})


test('Cannot like posts of a user that has blocked us', async () => {
  // us and them
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // they add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await theirClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()

  // they block us
  resp = await theirClient.mutate({mutation: mutations.blockUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we cannot like their post
  variables = {postId}
  await expect(ourClient.mutate({mutation: mutations.onymouslyLikePost, variables})).rejects.toThrow('ClientError')
  await expect(ourClient.mutate({mutation: mutations.anonymouslyLikePost, variables})).rejects.toThrow('ClientError')

  // they unblock us
  resp = await theirClient.mutate({mutation: mutations.unblockUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we can like their post
  resp = await ourClient.mutate({mutation: mutations.onymouslyLikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['onymouslyLikePost']['likeStatus']).toBe('ONYMOUSLY_LIKED')
  resp = await ourClient.mutate({mutation: mutations.dislikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['dislikePost']['likeStatus']).toBe('NOT_LIKED')
  resp = await ourClient.mutate({mutation: mutations.anonymouslyLikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['anonymouslyLikePost']['likeStatus']).toBe('ANONYMOUSLY_LIKED')
})


test('Cannot like posts of a user we have blocked', async () => {
  // us and them
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // they add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await theirClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()

  // we block them
  resp = await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we cannot like their post
  variables = {postId}
  await expect(ourClient.mutate({mutation: mutations.onymouslyLikePost, variables})).rejects.toThrow('ClientError')
  await expect(ourClient.mutate({mutation: mutations.anonymouslyLikePost, variables})).rejects.toThrow('ClientError')

  // we unblock them
  resp = await ourClient.mutate({mutation: mutations.unblockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we can like their post
  resp = await ourClient.mutate({mutation: mutations.onymouslyLikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['onymouslyLikePost']['likeStatus']).toBe('ONYMOUSLY_LIKED')
  resp = await ourClient.mutate({mutation: mutations.dislikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['dislikePost']['likeStatus']).toBe('NOT_LIKED')
  resp = await ourClient.mutate({mutation: mutations.anonymouslyLikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['anonymouslyLikePost']['likeStatus']).toBe('ANONYMOUSLY_LIKED')
})


test('Can only like posts of private users if we are a follower of theirs', async () => {
  // us and another private user
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()
  let variables = {privacyStatus: 'PRIVATE'}
  let resp = await theirClient.mutate({mutation: mutations.setUserPrivacyStatus, variables})
  expect(resp['errors']).toBeUndefined()

  // they add a post
  const postId = uuidv4()
  variables = {postId, imageData, lifetime: 'P1D'}
  resp = await theirClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()

  // verify we cannot like that post
  variables = {postId}
  await expect(ourClient.mutate({mutation: mutations.onymouslyLikePost, variables})).rejects.toThrow('ClientError')
  await expect(ourClient.mutate({mutation: mutations.anonymouslyLikePost, variables})).rejects.toThrow('ClientError')

  // we request to follow them
  resp =  await ourClient.mutate({mutation: mutations.followUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we cannot like that post
  variables = {postId}
  await expect(ourClient.mutate({mutation: mutations.onymouslyLikePost, variables})).rejects.toThrow('ClientError')
  await expect(ourClient.mutate({mutation: mutations.anonymouslyLikePost, variables})).rejects.toThrow('ClientError')

  // they deny our follow request
  resp = await theirClient.mutate({mutation: mutations.denyFollowerUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we cannot like that post
  variables = {postId}
  await expect(ourClient.mutate({mutation: mutations.onymouslyLikePost, variables})).rejects.toThrow('ClientError')
  await expect(ourClient.mutate({mutation: mutations.anonymouslyLikePost, variables})).rejects.toThrow('ClientError')

  // they accept our follow request
  resp = await theirClient.mutate({mutation: mutations.acceptFollowerUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()

  // verify we *can* like that post
  resp = await ourClient.mutate({mutation: mutations.onymouslyLikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['onymouslyLikePost']['likeStatus']).toBe('ONYMOUSLY_LIKED')
  resp = await ourClient.mutate({mutation: mutations.dislikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['dislikePost']['likeStatus']).toBe('NOT_LIKED')
  resp = await ourClient.mutate({mutation: mutations.anonymouslyLikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['anonymouslyLikePost']['likeStatus']).toBe('ANONYMOUSLY_LIKED')
})


test('Onymously like, then dislike, a post', async () => {
  // we add a post
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()

  // check that post shows no sign of likes
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  let post = resp['data']['post']
  expect(post['likeStatus']).toBe('NOT_LIKED')
  expect(post['onymousLikeCount']).toBe(0)
  expect(post['onymouslyLikedBy']['items']).toHaveLength(0)

  // we onymously like that post
  resp = await ourClient.mutate({mutation: mutations.onymouslyLikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['onymouslyLikePost']
  expect(post['likeStatus']).toBe('ONYMOUSLY_LIKED')
  expect(post['anonymousLikeCount']).toBe(0)
  expect(post['onymousLikeCount']).toBe(1)
  expect(post['onymouslyLikedBy']['items']).toHaveLength(1)
  expect(post['onymouslyLikedBy']['items'][0]['userId']).toBe(ourUserId)

  // check that like shows up on the post
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['post']
  expect(post['likeStatus']).toBe('ONYMOUSLY_LIKED')
  expect(post['anonymousLikeCount']).toBe(0)
  expect(post['onymousLikeCount']).toBe(1)
  expect(post['onymouslyLikedBy']['items']).toHaveLength(1)
  expect(post['onymouslyLikedBy']['items'][0]['userId']).toBe(ourUserId)

  // check our list of liked posts
  resp = await ourClient.query({query: queries.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['onymouslyLikedPosts']['items']).toHaveLength(1)
  expect(resp['data']['self']['onymouslyLikedPosts']['items'][0]['postId']).toBe(postId)

  // dislike the post
  resp = await ourClient.mutate({mutation: mutations.dislikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['dislikePost']
  expect(post['likeStatus']).toBe('NOT_LIKED')
  expect(post['anonymousLikeCount']).toBe(0)
  expect(post['onymousLikeCount']).toBe(0)
  expect(post['onymouslyLikedBy']['items']).toHaveLength(0)

  // check the like has disappeared from the post
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['post']
  expect(post['likeStatus']).toBe('NOT_LIKED')
  expect(post['anonymousLikeCount']).toBe(0)
  expect(post['onymousLikeCount']).toBe(0)
  expect(post['onymouslyLikedBy']['items']).toHaveLength(0)

  // check our list of liked posts is now empty
  resp = await ourClient.query({query: queries.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['onymouslyLikedPosts']['items']).toHaveLength(0)
})


test('Anonymously like, then dislike, a post', async () => {
  // we add a post
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()

  // check that post shows no sign of likes
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  let post = resp['data']['post']
  expect(post['likeStatus']).toBe('NOT_LIKED')
  expect(post['anonymousLikeCount']).toBe(0)
  expect(post['onymouslyLikedBy']['items']).toHaveLength(0)

  // we anonymously like that post
  resp = await ourClient.mutate({mutation: mutations.anonymouslyLikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['anonymouslyLikePost']
  expect(post['likeStatus']).toBe('ANONYMOUSLY_LIKED')
  expect(post['anonymousLikeCount']).toBe(1)
  expect(post['onymousLikeCount']).toBe(0)
  expect(post['onymouslyLikedBy']['items']).toHaveLength(0)

  // check that like shows up on the post
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['post']
  expect(post['likeStatus']).toBe('ANONYMOUSLY_LIKED')
  expect(post['anonymousLikeCount']).toBe(1)
  expect(post['onymousLikeCount']).toBe(0)
  expect(post['onymouslyLikedBy']['items']).toHaveLength(0)

  // check our list of liked posts
  resp = await ourClient.query({query: queries.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['anonymouslyLikedPosts']['items']).toHaveLength(1)
  expect(resp['data']['self']['anonymouslyLikedPosts']['items'][0]['postId']).toBe(postId)

  // dislike the post
  resp = await ourClient.mutate({mutation: mutations.dislikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['dislikePost']
  expect(post['likeStatus']).toBe('NOT_LIKED')
  expect(post['anonymousLikeCount']).toBe(0)
  expect(post['onymousLikeCount']).toBe(0)
  expect(post['onymouslyLikedBy']['items']).toHaveLength(0)

  // check the like has disappeared from the post
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['post']
  expect(post['likeStatus']).toBe('NOT_LIKED')
  expect(post['anonymousLikeCount']).toBe(0)
  expect(post['onymousLikeCount']).toBe(0)
  expect(post['onymouslyLikedBy']['items']).toHaveLength(0)

  // check our list of liked posts is now empty
  resp = await ourClient.query({query: queries.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['anonymouslyLikedPosts']['items']).toHaveLength(0)
})


test('Like counts show up for posts in feed', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  await misc.sleep(1000)  // let dynamo converge

  // get that post from our feed, check its like counts
  resp = await ourClient.query({query: queries.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(1)
  expect(resp['data']['self']['feed']['items'][0]['postId']).toBe(postId)
  expect(resp['data']['self']['feed']['items'][0]['onymousLikeCount']).toBe(0)
  expect(resp['data']['self']['feed']['items'][0]['anonymousLikeCount']).toBe(0)

  // we like it onymously, they like it anonymously
  resp = await ourClient.mutate({mutation: mutations.onymouslyLikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  resp = await theirClient.mutate({mutation: mutations.anonymouslyLikePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()

  // get that post from our feed again, check its like counts
  resp = await ourClient.query({query: queries.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(1)
  expect(resp['data']['self']['feed']['items'][0]['postId']).toBe(postId)
  expect(resp['data']['self']['feed']['items'][0]['onymousLikeCount']).toBe(1)
  expect(resp['data']['self']['feed']['items'][0]['anonymousLikeCount']).toBe(1)
})
