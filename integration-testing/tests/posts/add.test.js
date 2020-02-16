/* eslint-env jest */

const moment = require('moment')
const rp = require('request-promise-native')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const schema = require('../../utils/schema.js')

const imageContentType = 'image/jpeg'
const imageData = misc.generateRandomJpeg(300, 200)
const imageDataB64 = new Buffer.from(imageData).toString('base64')
const imageData2 = misc.generateRandomJpeg(300, 200)

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Add post no expiration', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId, imageData: imageDataB64}})
  expect(resp['errors']).toBeUndefined()
  let post = resp['data']['addPost']
  expect(post['postId']).toBe(postId)
  expect(post['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(post['expiresAt']).toBeNull()
  expect(post['originalPost']['postId']).toBe(postId)

  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['post']
  expect(post['postId']).toBe(postId)
  expect(post['expiresAt']).toBeNull()
  expect(post['originalPost']['postId']).toBe(postId)

  resp = await ourClient.query({query: schema.userPosts, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toHaveLength(1)
  post = resp['data']['user']['posts']['items'][0]
  expect(post['postId']).toBe(postId)
  expect(post['postedBy']['userId']).toBe(ourUserId)
  expect(post['expiresAt']).toBeNull()

  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(1)
  expect(resp['data']['self']['feed']['items'][0]['postId']).toEqual(postId)
})


test('Add post with expiration', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  const [postId, mediaId] = [uuidv4(), uuidv4()]
  const text = 'zeds dead baby, zeds dead'
  const lifetime = 'P7D'
  let resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, text, lifetime, mediaId}})
  expect(resp['errors']).toBeUndefined()
  const post = resp['data']['addPost']
  expect(post['postId']).toBe(postId)
  expect(post['text']).toBe(text)
  expect(post['postedAt']).not.toBeNull()
  expect(post['expiresAt']).not.toBeNull()
  const expected_expires_at = moment(post['postedAt'])
  expected_expires_at.add(moment.duration(lifetime))
  const expires_at = moment(post['expiresAt'])
  expect(expires_at.isSame(expected_expires_at)).toBe(true)
})


test('Add media post with image data directly included', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // add the post with image data included in the gql call
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId, imageData: imageDataB64}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['addPost']['mediaObjects']).toHaveLength(1)
  const media = resp['data']['addPost']['mediaObjects'][0]
  expect(media['mediaId']).toBe(mediaId)
  expect(media['mediaStatus']).toBe('UPLOADED')
  expect(media['uploadUrl']).toBeNull()
  expect(media['url']).not.toBeNull()

  // verify we can access all of the urls
  await rp.head({uri: media['url'], simple: true})
  await rp.head({uri: media['url4k'], simple: true})
  await rp.head({uri: media['url1080p'], simple: true})
  await rp.head({uri: media['url480p'], simple: true})
  await rp.head({uri: media['url64p'], simple: true})

  // check the data in the native image is correct
  const s3ImageData = await rp.get({uri: media['url'], encoding: null})
  expect(s3ImageData.equals(imageData)).toBe(true)

  // double check everything saved to db correctly
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['post']['mediaObjects']).toHaveLength(1)
  const mediaCheck = resp['data']['post']['mediaObjects'][0]
  expect(mediaCheck['mediaId']).toBe(mediaId)
  expect(mediaCheck['mediaStatus']).toBe('UPLOADED')
  expect(mediaCheck['uploadUrl']).toBeNull()

  expect(mediaCheck['url'].split('?')[0]).toBe(media['url'].split('?')[0])
  expect(mediaCheck['url4k'].split('?')[0]).toBe(media['url4k'].split('?')[0])
  expect(mediaCheck['url1080p'].split('?')[0]).toBe(media['url1080p'].split('?')[0])
  expect(mediaCheck['url480p'].split('?')[0]).toBe(media['url480p'].split('?')[0])
  expect(mediaCheck['url64p'].split('?')[0]).toBe(media['url64p'].split('?')[0])
})


test('Add media post, check non-duplicates are not marked as such', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add a media post, give s3 trigger a second to fire
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId}})
  expect(resp['errors']).toBeUndefined()
  let post = resp['data']['addPost']
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('PENDING')
  expect(post['mediaObjects']).toHaveLength(1)
  expect(post['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(post['mediaObjects'][0]['mediaStatus']).toBe('AWAITING_UPLOAD')
  expect(post['mediaObjects'][0]['uploadUrl']).toBeTruthy()
  expect(post['mediaObjects'][0]['url']).toBeNull()
  let uploadUrl = post['mediaObjects'][0]['uploadUrl']

  // upload the media, give S3 trigger a second to fire
  await misc.uploadMedia(imageData, imageContentType, uploadUrl)
  await misc.sleepUntilPostCompleted(ourClient, postId)

  // add another media post with a different image
  const [postId2, mediaId2] = [uuidv4(), uuidv4()]
  resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId: postId2, mediaId: mediaId2}})
  expect(resp['errors']).toBeUndefined()
  uploadUrl = resp['data']['addPost']['mediaObjects'][0]['uploadUrl']
  await misc.uploadMedia(imageData2, imageContentType, uploadUrl)
  await misc.sleepUntilPostCompleted(ourClient, postId2)

  // check the post & media have changed status and look good
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['post']
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('COMPLETED')
  expect(post['originalPost']['postId']).toBe(postId)
  expect(post['mediaObjects']).toHaveLength(1)
  expect(post['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(post['mediaObjects'][0]['mediaStatus']).toBe('UPLOADED')
  expect(post['mediaObjects'][0]['isVerified']).toBe(false)
  expect(post['mediaObjects'][0]['uploadUrl']).toBeNull()
  expect(post['mediaObjects'][0]['url']).toBeTruthy()

  // check the originalPost properties don't point at each other
  resp = await ourClient.query({query: schema.post, variables: {postId: postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['post']['originalPost']['postId']).toBe(postId)
  resp = await ourClient.query({query: schema.post, variables: {postId: postId2}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId2)
  expect(resp['data']['post']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['post']['originalPost']['postId']).toBe(postId2)
})


test('Cannot add post with invalid lifetime', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const variables = {postId: uuidv4(), mediaId: uuidv4()}

  // malformed duration string
  variables.lifetime = 'invalid'
  await expect(ourClient.mutate({mutation: schema.addPost, variables})).rejects.toThrow()

  // negative value for lifetime
  variables.lifetime = '-P1D'
  await expect(ourClient.mutate({mutation: schema.addPost, variables})).rejects.toThrow()

  // zero value for lifetime
  variables.lifetime = 'P0D'
  await expect(ourClient.mutate({mutation: schema.addPost, variables})).rejects.toThrow()

  // success!
  variables.lifetime = 'P1D'
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
})


test('Mental health settings default values', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // no user-level settings set
  let variables = {postId: uuidv4(), mediaId: uuidv4()}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(variables.postId)
  expect(resp['data']['addPost']['commentsDisabled']).toBe(false)
  expect(resp['data']['addPost']['likesDisabled']).toBe(false)
  expect(resp['data']['addPost']['sharingDisabled']).toBe(false)
  expect(resp['data']['addPost']['verificationHidden']).toBe(false)

  // set user-level mental health settings to true (which provide the defaults)
  variables = {commentsDisabled: true, likesDisabled: true, sharingDisabled: true, verificationHidden: true}
  resp = await ourClient.mutate({mutation: schema.setUserMentalHealthSettings, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['userId']).toBe(ourUserId)
  expect(resp['data']['setUserDetails']['commentsDisabled']).toBe(true)
  expect(resp['data']['setUserDetails']['likesDisabled']).toBe(true)
  expect(resp['data']['setUserDetails']['sharingDisabled']).toBe(true)
  expect(resp['data']['setUserDetails']['verificationHidden']).toBe(true)

  // check those new user-level settings are used as defaults for a new post
  variables = {postId: uuidv4(), mediaId: uuidv4()}
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(variables.postId)
  expect(resp['data']['addPost']['commentsDisabled']).toBe(true)
  expect(resp['data']['addPost']['likesDisabled']).toBe(true)
  expect(resp['data']['addPost']['sharingDisabled']).toBe(true)
  expect(resp['data']['addPost']['verificationHidden']).toBe(true)

  // change the user-level mental health setting defaults
  variables = {commentsDisabled: false, likesDisabled: false, sharingDisabled: false, verificationHidden: false}
  resp = await ourClient.mutate({mutation: schema.setUserMentalHealthSettings, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['userId']).toBe(ourUserId)
  expect(resp['data']['setUserDetails']['commentsDisabled']).toBe(false)
  expect(resp['data']['setUserDetails']['likesDisabled']).toBe(false)
  expect(resp['data']['setUserDetails']['sharingDisabled']).toBe(false)
  expect(resp['data']['setUserDetails']['verificationHidden']).toBe(false)

  // check those new user-level settings are used as defaults for a new post
  variables = {postId: uuidv4(), mediaId: uuidv4()}
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(variables.postId)
  expect(resp['data']['addPost']['commentsDisabled']).toBe(false)
  expect(resp['data']['addPost']['likesDisabled']).toBe(false)
  expect(resp['data']['addPost']['sharingDisabled']).toBe(false)
  expect(resp['data']['addPost']['verificationHidden']).toBe(false)
})


test('Mental health settings specify values', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // create a post, specify both to false
  let postId = uuidv4()
  let variables = {
    postId,
    mediaId: uuidv4(),
    commentsDisabled: false,
    likesDisabled: false,
    sharingDisabled: false,
    verificationHidden: false,
  }
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['commentsDisabled']).toBe(false)
  expect(resp['data']['addPost']['likesDisabled']).toBe(false)
  expect(resp['data']['addPost']['sharingDisabled']).toBe(false)
  expect(resp['data']['addPost']['verificationHidden']).toBe(false)

  // double check those values stuck
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['commentsDisabled']).toBe(false)
  expect(resp['data']['post']['likesDisabled']).toBe(false)
  expect(resp['data']['post']['sharingDisabled']).toBe(false)
  expect(resp['data']['post']['verificationHidden']).toBe(false)

  // create a post, specify both to true
  postId = uuidv4()
  variables = {
    postId,
    mediaId: uuidv4(),
    commentsDisabled: true,
    likesDisabled: true,
    sharingDisabled: true,
    verificationHidden: true,
  }
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['commentsDisabled']).toBe(true)
  expect(resp['data']['addPost']['likesDisabled']).toBe(true)
  expect(resp['data']['addPost']['sharingDisabled']).toBe(true)
  expect(resp['data']['addPost']['verificationHidden']).toBe(true)

  // double check those values stuck
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['commentsDisabled']).toBe(true)
  expect(resp['data']['post']['likesDisabled']).toBe(true)
  expect(resp['data']['post']['sharingDisabled']).toBe(true)
  expect(resp['data']['post']['verificationHidden']).toBe(true)
})


test('Post.originalPost - duplicates caught on creation, privacy', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  const ourPostId = uuidv4()
  const theirPostId = uuidv4()

  // we add a media post, complete it, check it's original
  let variables = {postId: ourPostId, mediaId: uuidv4(), imageData: imageDataB64}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(ourPostId)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['addPost']['originalPost']['postId']).toBe(ourPostId)

  // they add another media post with the same media, original should point back to first post
  variables = {postId: theirPostId, mediaId: uuidv4(), imageData: imageDataB64}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(theirPostId)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['addPost']['originalPost']['postId']).toBe(ourPostId)

  // check each others post objects directly
  resp = await theirClient.query({query: schema.post, variables: {postId: ourPostId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(ourPostId)
  expect(resp['data']['post']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['post']['originalPost']['postId']).toBe(ourPostId)
  resp = await ourClient.query({query: schema.post, variables: {postId: theirPostId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(theirPostId)
  expect(resp['data']['post']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['post']['originalPost']['postId']).toBe(ourPostId)

  // we block them
  resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(theirUserId)
  expect(resp['data']['blockUser']['blockedStatus']).toBe('BLOCKING')

  // verify they can't see their post's originalPost
  resp = await theirClient.query({query: schema.post, variables: {postId: theirPostId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(theirPostId)
  expect(resp['data']['post']['originalPost']).toBeNull()

  // we unblock them
  resp = await ourClient.mutate({mutation: schema.unblockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['unblockUser']['userId']).toBe(theirUserId)
  expect(resp['data']['unblockUser']['blockedStatus']).toBe('NOT_BLOCKING')

  // we go private
  resp = await ourClient.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['privacyStatus']).toBe('PRIVATE')

  // verify they can't see their post's originalPost
  resp = await theirClient.query({query: schema.post, variables: {postId: theirPostId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(theirPostId)
  expect(resp['data']['post']['originalPost']).toBeNull()

  // they request to follow us, we accept
  resp = await theirClient.mutate({mutation: schema.followUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('REQUESTED')
  resp = await ourClient.mutate({mutation: schema.acceptFollowerUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['acceptFollowerUser']['followerStatus']).toBe('FOLLOWING')

  // verify they *can* see their post's originalPost
  resp = await theirClient.query({query: schema.post, variables: {postId: theirPostId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(theirPostId)
  expect(resp['data']['post']['originalPost']['postId']).toBe(ourPostId)
})
