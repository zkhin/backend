/* eslint-env jest */

const moment = require('moment')
const rp = require('request-promise-native')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const schema = require('../../utils/schema.js')

const imageBytes = misc.generateRandomJpeg(300, 200)
const imageData = new Buffer.from(imageBytes).toString('base64')
const imageBytes2 = misc.generateRandomJpeg(300, 200)
const imageHeaders = {'Content-Type': 'image/jpeg'}

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
  let resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId, imageData}})
  expect(resp['errors']).toBeUndefined()
  let post = resp['data']['addPost']
  expect(post['postId']).toBe(postId)
  expect(post['postType']).toBe('IMAGE')
  expect(post['postStatus']).toBe('COMPLETED')
  expect(post['expiresAt']).toBeNull()
  expect(post['originalPost']['postId']).toBe(postId)
  await misc.sleep(2000)  // let dynamo converge

  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['post']
  expect(post['postId']).toBe(postId)
  expect(post['postType']).toBe('IMAGE')
  expect(post['postStatus']).toBe('COMPLETED')
  expect(post['expiresAt']).toBeNull()
  expect(post['originalPost']['postId']).toBe(postId)

  resp = await ourClient.query({query: schema.userPosts, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['posts']['items']).toHaveLength(1)
  post = resp['data']['user']['posts']['items'][0]
  expect(post['postId']).toBe(postId)
  expect(post['postType']).toBe('IMAGE')
  expect(post['postStatus']).toBe('COMPLETED')
  expect(post['postedBy']['userId']).toBe(ourUserId)
  expect(post['expiresAt']).toBeNull()

  resp = await ourClient.query({query: schema.selfFeed})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['feed']['items']).toHaveLength(1)
  expect(resp['data']['self']['feed']['items'][0]['postId']).toEqual(postId)
  expect(resp['data']['self']['feed']['items'][0]['postType']).toBe('IMAGE')
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
  expect(post['postType']).toBe('IMAGE')
  expect(post['postStatus']).toBe('PENDING')
  expect(post['text']).toBe(text)
  expect(post['postedAt']).toBeTruthy()
  expect(post['expiresAt']).toBeTruthy()
  const expected_expires_at = moment(post['postedAt'])
  expected_expires_at.add(moment.duration(lifetime))
  const expires_at = moment(post['expiresAt'])
  expect(expires_at.isSame(expected_expires_at)).toBe(true)
})


test('Add text-only post', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  const postId = uuidv4()
  const text = 'zeds dead baby, zeds dead'

  // check can't add it without specifying postType
  let variables = {postId, text}
  await expect(ourClient.mutate({mutation: schema.addPostNoMedia, variables})).rejects.toThrow('ClientError')

  variables = {postId, text, postType: 'TEXT_ONLY'}
  let resp = await ourClient.mutate({mutation: schema.addPostNoMedia, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postType']).toBe('TEXT_ONLY')
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['addPost']['text']).toBe(text)
  expect(resp['data']['addPost']['isVerified']).toBeNull()
  expect(resp['data']['addPost']['image']).toBeNull()
  expect(resp['data']['addPost']['imageUploadUrl']).toBeNull()
})


test('Add pending video post minimal', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  const postId = uuidv4()
  let variables = {postId, postType: 'VIDEO'}
  let resp = await ourClient.mutate({mutation: schema.addPostNoMedia, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postType']).toBe('VIDEO')
  expect(resp['data']['addPost']['postStatus']).toBe('PENDING')
  expect(resp['data']['addPost']['videoUploadUrl']).toBeTruthy()
  expect(resp['data']['addPost']['text']).toBeNull()
  expect(resp['data']['addPost']['isVerified']).toBeNull()
  expect(resp['data']['addPost']['image']).toBeNull()
  expect(resp['data']['addPost']['imageUploadUrl']).toBeNull()
  expect(resp['data']['addPost']['commentsDisabled']).toBe(false)
  expect(resp['data']['addPost']['likesDisabled']).toBe(false)
  expect(resp['data']['addPost']['sharingDisabled']).toBe(false)
  expect(resp['data']['addPost']['verificationHidden']).toBe(false)
})


test('Add pending video post maximal', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  const postId = uuidv4()
  const text = 'lore ipsum'
  let variables = {
    postId,
    postType: 'VIDEO',
    text,
    commentsDisabled: true,
    likesDisabled: true,
    sharingDisabled: true,
    verificationHidden: true,
  }
  let resp = await ourClient.mutate({mutation: schema.addPostNoMedia, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postType']).toBe('VIDEO')
  expect(resp['data']['addPost']['postStatus']).toBe('PENDING')
  expect(resp['data']['addPost']['videoUploadUrl']).toBeTruthy()
  expect(resp['data']['addPost']['text']).toBe(text)
  expect(resp['data']['addPost']['isVerified']).toBe(true)
  expect(resp['data']['addPost']['image']).toBeNull()
  expect(resp['data']['addPost']['imageUploadUrl']).toBeNull()
  expect(resp['data']['addPost']['commentsDisabled']).toBe(true)
  expect(resp['data']['addPost']['likesDisabled']).toBe(true)
  expect(resp['data']['addPost']['sharingDisabled']).toBe(true)
  expect(resp['data']['addPost']['verificationHidden']).toBe(true)
})


test('Cant add video post to album (yet)', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  const postId = uuidv4()
  let variables = {postId, postType: 'VIDEO', albumId: 'aid'}
  await expect(ourClient.mutate({mutation: schema.addPost, variables})).rejects.toThrow()
})


test('Add image post with image data directly included', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // add the post with image data included in the gql call
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId, imageData}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postType']).toBe('IMAGE')
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['addPost']['imageUploadUrl']).toBeNull()
  const image = resp['data']['addPost']['image']
  expect(image['url']).toBeTruthy()

  // verify we can access all of the urls
  await rp.head({uri: image['url'], simple: true})
  await rp.head({uri: image['url4k'], simple: true})
  await rp.head({uri: image['url1080p'], simple: true})
  await rp.head({uri: image['url480p'], simple: true})
  await rp.head({uri: image['url64p'], simple: true})

  // check the data in the native image is correct
  const s3ImageData = await rp.get({uri: image['url'], encoding: null})
  expect(s3ImageData.equals(imageBytes)).toBe(true)

  // double check everything saved to db correctly
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['post']['imageUploadUrl']).toBeNull()
  const imageCheck = resp['data']['post']['image']

  expect(imageCheck['url'].split('?')[0]).toBe(image['url'].split('?')[0])
  expect(imageCheck['url4k'].split('?')[0]).toBe(image['url4k'].split('?')[0])
  expect(imageCheck['url1080p'].split('?')[0]).toBe(image['url1080p'].split('?')[0])
  expect(imageCheck['url480p'].split('?')[0]).toBe(image['url480p'].split('?')[0])
  expect(imageCheck['url64p'].split('?')[0]).toBe(image['url64p'].split('?')[0])
})


test('Add image post (with postType specified), check non-duplicates are not marked as such', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add a image post, give s3 trigger a second to fire
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId, postType: 'IMAGE'}})
  expect(resp['errors']).toBeUndefined()
  let post = resp['data']['addPost']
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('PENDING')
  expect(post['imageUploadUrl']).toBeTruthy()
  expect(post['image']).toBeNull()
  let uploadUrl = post['imageUploadUrl']

  // upload the image, give S3 trigger a second to fire
  await rp.put({url: uploadUrl, headers: imageHeaders, body: imageBytes})
  await misc.sleepUntilPostCompleted(ourClient, postId)

  // add another image post with a different image
  const [postId2, mediaId2] = [uuidv4(), uuidv4()]
  resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId: postId2, mediaId: mediaId2}})
  expect(resp['errors']).toBeUndefined()
  uploadUrl = resp['data']['addPost']['imageUploadUrl']
  await rp.put({url: uploadUrl, headers: imageHeaders, body: imageBytes2})
  await misc.sleepUntilPostCompleted(ourClient, postId2)

  // check the post has changed status and looks good
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  post = resp['data']['post']
  expect(post['postId']).toBe(postId)
  expect(post['postStatus']).toBe('COMPLETED')
  expect(post['imageUploadUrl']).toBeNull()
  expect(post['image']['url']).toBeTruthy()
  expect(post['originalPost']['postId']).toBe(postId)

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


test('Add post with text of empty string same as null text', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()
  let resp = await ourClient.mutate({mutation: schema.addPost, variables: {postId, mediaId: uuidv4(), text: ''}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postType']).toBe('IMAGE')
  expect(resp['data']['addPost']['postStatus']).toBe('PENDING')
  expect(resp['data']['addPost']['text']).toBeNull()
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

  // we add a image post, complete it, check it's original
  let variables = {postId: ourPostId, mediaId: uuidv4(), imageData}
  let resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(ourPostId)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['addPost']['originalPost']['postId']).toBe(ourPostId)
  await misc.sleep(1000)  // let dynamo converge

  // they add another image post with the same image, original should point back to first post
  variables = {postId: theirPostId, mediaId: uuidv4(), imageData}
  resp = await theirClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(theirPostId)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['addPost']['originalPost']['postId']).toBe(ourPostId)
  await misc.sleep(1000)  // let dynamo converge

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
