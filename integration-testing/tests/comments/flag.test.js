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
afterAll(async () => await loginCache.reset())


test('Cant flag our own comment', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // they add a post
  const postId = uuidv4()
  let resp = await theirClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)

  // we add a comment to that post
  const commentId = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addComment, variables: {commentId, postId, text: 'lore'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addComment.commentId).toBe(commentId)

  // verify we cant flag that comment
  await expect(ourClient.mutate({mutation: mutations.flagComment, variables: {commentId}}))
    .rejects.toThrow(/ClientError: .* their own comment /)

  // check the comment flagStatus shows we did not flag it
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.comments.items[0].commentId).toBe(commentId)
  expect(resp.data.post.comments.items[0].flagStatus).toBe('NOT_FLAGGED')
})



test('Anybody can flag a comment of private user on post of public user', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // they go private
  const privacyStatus = 'PRIVATE'
  let resp = await theirClient.mutate({mutation: mutations.setUserPrivacyStatus, variables: {privacyStatus}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.setUserDetails.userId).toBe(theirUserId)
  expect(resp.data.setUserDetails.privacyStatus).toBe(privacyStatus)

  // we add a post
  const postId = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)

  // they comment on the post
  const commentId = uuidv4()
  resp = await theirClient.mutate({mutation: mutations.addComment, variables: {commentId, postId, text: 'lore'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addComment.commentId).toBe(commentId)

  // verify we can flag that comment
  resp = await ourClient.mutate({mutation: mutations.flagComment, variables: {commentId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.flagComment.commentId).toBe(commentId)
  expect(resp.data.flagComment.flagStatus).toBe('FLAGGED')

  // double check the flag status
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.comments.items[0].commentId).toBe(commentId)
  expect(resp.data.post.comments.items[0].flagStatus).toBe('FLAGGED')

  // verify we can't double-flag
  await expect(ourClient.mutate({mutation: mutations.flagComment, variables: {commentId}}))
    .rejects.toThrow(/ClientError: .* has already been flagged /)
})


test('Cant flag a comment if we are disabled', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // they add a post
  const postId = uuidv4()
  let resp = await theirClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)

  // they add a comment to their post
  const commentId = uuidv4()
  resp = await theirClient.mutate({mutation: mutations.addComment, variables: {commentId, postId, text: 'lore'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addComment.commentId).toBe(commentId)

  // we disable ourselves
  resp = await ourClient.mutate({mutation: mutations.disableUser})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.disableUser.userId).toBe(ourUserId)
  expect(resp.data.disableUser.userStatus).toBe('DISABLED')

  // verify we can't flag their comment
  await expect(ourClient.mutate({mutation: mutations.flagComment, variables: {commentId}}))
    .rejects.toThrow(/ClientError: User .* is not ACTIVE/)
})


test('Follower can flag comment on post of private user, non-follower cannot', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)

  // we add a comment to our post
  const commentId = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addComment, variables: {commentId, postId, text: 'lore'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addComment.commentId).toBe(commentId)

  // we go private
  resp = await ourClient.mutate({mutation: mutations.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.setUserDetails.userId).toBe(ourUserId)
  expect(resp.data.setUserDetails.privacyStatus).toBe('PRIVATE')

  // verify they can't flag their comment
  await expect(theirClient.mutate({mutation: mutations.flagComment, variables: {commentId}}))
    .rejects.toThrow(/ClientError: User does not have access /)

  // they request to follow us
  resp = await theirClient.mutate({mutation: mutations.followUser, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.followUser.followedStatus).toBe('REQUESTED')

  // we accept their follow requqest
  resp = await ourClient.mutate({mutation: mutations.acceptFollowerUser, variables: {userId: theirUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.acceptFollowerUser.followerStatus).toBe('FOLLOWING')

  // verify they have not flagged the comment
  resp = await theirClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.comments.items[0].commentId).toBe(commentId)
  expect(resp.data.post.comments.items[0].flagStatus).toBe('NOT_FLAGGED')

  // verify they can now flag the comment
  resp = await theirClient.mutate({mutation: mutations.flagComment, variables: {commentId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.flagComment.commentId).toBe(commentId)
  expect(resp.data.flagComment.flagStatus).toBe('FLAGGED')

  // verify the comment flag stuck
  resp = await theirClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.comments.items[0].commentId).toBe(commentId)
  expect(resp.data.post.comments.items[0].flagStatus).toBe('FLAGGED')
})


test('Cannot flag comment that does not exist', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // try to flag a non-existent post
  const commentId = uuidv4()
  await expect(ourClient.mutate({mutation: mutations.flagComment, variables: {commentId}}))
    .rejects.toThrow(/ClientError: Comment .* does not exist/)
})


test('Cannot flag comment of user that has blocked us', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // they add a post
  const postId = uuidv4()
  let resp = await theirClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)

  // they add a comment to their post
  const commentId = uuidv4()
  resp = await theirClient.mutate({mutation: mutations.addComment, variables: {commentId, postId, text: 'lore'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addComment.commentId).toBe(commentId)

  // they block us
  resp = await theirClient.mutate({mutation: mutations.blockUser, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.blockUser.userId).toBe(ourUserId)
  expect(resp.data.blockUser.blockedStatus).toBe('BLOCKING')

  // verify we cannot flag their comment
  await expect(ourClient.mutate({mutation: mutations.flagComment, variables: {commentId}}))
    .rejects.toThrow(/ClientError: .* has been blocked by owner /)

  // they unblock us
  resp = await theirClient.mutate({mutation: mutations.unblockUser, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.unblockUser.userId).toBe(ourUserId)
  expect(resp.data.unblockUser.blockedStatus).toBe('NOT_BLOCKING')

  // verify we can flag their comment
  resp = await ourClient.mutate({mutation: mutations.flagComment, variables: {commentId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.flagComment.flagStatus).toBe('FLAGGED')
})


test('Cannot flag comment of user we have blocked', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // they add a post
  const postId = uuidv4()
  let resp = await theirClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)

  // they add a comment to their post
  const commentId = uuidv4()
  resp = await theirClient.mutate({mutation: mutations.addComment, variables: {commentId, postId, text: 'lore'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addComment.commentId).toBe(commentId)

  // we block them
  resp = await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: theirUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.blockUser.userId).toBe(theirUserId)
  expect(resp.data.blockUser.blockedStatus).toBe('BLOCKING')

  // verify we cannot flag their comment
  await expect(ourClient.mutate({mutation: mutations.flagComment, variables: {commentId}}))
    .rejects.toThrow(/ClientError: .* has blocked owner /)

  // we unblock them
  resp = await ourClient.mutate({mutation: mutations.unblockUser, variables: {userId: theirUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.unblockUser.userId).toBe(theirUserId)
  expect(resp.data.unblockUser.blockedStatus).toBe('NOT_BLOCKING')

  // verify we can flag their comment
  resp = await ourClient.mutate({mutation: mutations.flagComment, variables: {commentId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.flagComment.flagStatus).toBe('FLAGGED')
})
