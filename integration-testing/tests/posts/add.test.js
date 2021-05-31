const dayjs = require('dayjs')
const duration = require('dayjs/plugin/duration')
const {v4: uuidv4} = require('uuid')

const {cognito, eventually, generateRandomJpeg} = require('../../utils')
const {mutations, queries} = require('../../schema')

dayjs.extend(duration)
let anonClient
const imageBytes = generateRandomJpeg(300, 200)
const imageData = new Buffer.from(imageBytes).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())
afterEach(async () => {
  if (anonClient) await anonClient.mutate({mutation: mutations.deleteUser})
  anonClient = null
})

test('Add post no expiration', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()

  const postId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
  let post = resp.data.addPost
  expect(post.postId).toBe(postId)
  expect(post.postType).toBe('IMAGE')
  expect(post.postStatus).toBe('COMPLETED')
  expect(post.expiresAt).toBeNull()
  expect(post.originalPost.postId).toBe(postId)

  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.postType).toBe('IMAGE')
    expect(data.post.postStatus).toBe('COMPLETED')
    expect(data.post.expiresAt).toBeNull()
    expect(data.post.originalPost.postId).toBe(postId)
  })

  resp = await ourClient.query({query: queries.userPosts, variables: {userId: ourUserId}})
  expect(resp.data.user.posts.items).toHaveLength(1)
  post = resp.data.user.posts.items[0]
  expect(post.postId).toBe(postId)
  expect(post.postType).toBe('IMAGE')
  expect(post.postStatus).toBe('COMPLETED')
  expect(post.postedBy.userId).toBe(ourUserId)
  expect(post.expiresAt).toBeNull()

  resp = await ourClient.query({query: queries.selfFeed})
  expect(resp.data.self.feed.items).toHaveLength(1)
  expect(resp.data.self.feed.items[0].postId).toEqual(postId)
  expect(resp.data.self.feed.items[0].postType).toBe('IMAGE')
})

test('Add post with expiration', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()

  const postId = uuidv4()
  const text = 'zeds dead baby, zeds dead'
  const lifetime = 'P7D'
  let variables = {postId, text, lifetime}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  const post = resp.data.addPost
  expect(post.postId).toBe(postId)
  expect(post.postType).toBe('IMAGE')
  expect(post.postStatus).toBe('PENDING')
  expect(post.text).toBe(text)
  expect(post.postedAt).toBeTruthy()
  expect(post.expiresAt).toBeTruthy()
  const expected_expires_at = dayjs(post.postedAt).add(dayjs.duration(lifetime))
  const expires_at = dayjs(post.expiresAt)
  expect(expires_at.isSame(expected_expires_at)).toBe(true)
})

test('Add post with text of empty string same as null text', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const postId = uuidv4()
  let variables = {postId, text: ''}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postType).toBe('IMAGE')
  expect(resp.data.addPost.postStatus).toBe('PENDING')
  expect(resp.data.addPost.text).toBeNull()
})

test('Cannot add post with invalid lifetime', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const variables = {postId: uuidv4()}

  // malformed duration string
  variables.lifetime = 'invalid'
  await expect(ourClient.mutate({mutation: mutations.addPost, variables})).rejects.toThrow(
    /ClientError: Unable to parse lifetime /,
  )

  // negative value for lifetime
  variables.lifetime = '-P1D'
  await expect(ourClient.mutate({mutation: mutations.addPost, variables})).rejects.toThrow(
    /ClientError: Unable to parse lifetime /,
  ) // server-side lib doesn't support negative durations

  // zero value for lifetime
  variables.lifetime = 'P0D'
  await expect(ourClient.mutate({mutation: mutations.addPost, variables})).rejects.toThrow(
    /ClientError: .* with non-positive lifetime$/,
  )

  // success!
  variables.lifetime = 'P1D'
  await ourClient
    .mutate({mutation: mutations.addPost, variables})
    .then(({data}) => expect(data.addPost.postId).toBe(variables.postId))
})

test('Mental health settings default values', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()

  // no user-level settings set, system-level defaults should appear
  let variables = {postId: uuidv4()}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(variables.postId)
  expect(resp.data.addPost.commentsDisabled).toBe(false)
  expect(resp.data.addPost.likesDisabled).toBe(true)
  expect(resp.data.addPost.sharingDisabled).toBe(false)
  expect(resp.data.addPost.verificationHidden).toBe(false)

  // set user-level mental health settings to opposite of system defaults
  variables = {commentsDisabled: true, likesDisabled: false, sharingDisabled: true, verificationHidden: true}
  resp = await ourClient.mutate({mutation: mutations.setUserMentalHealthSettings, variables})
  expect(resp.data.setUserDetails.userId).toBe(ourUserId)
  expect(resp.data.setUserDetails.commentsDisabled).toBe(true)
  expect(resp.data.setUserDetails.likesDisabled).toBe(false)
  expect(resp.data.setUserDetails.sharingDisabled).toBe(true)
  expect(resp.data.setUserDetails.verificationHidden).toBe(true)

  // check those new user-level settings are used as defaults for a new post
  variables = {postId: uuidv4()}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(variables.postId)
  expect(resp.data.addPost.commentsDisabled).toBe(true)
  expect(resp.data.addPost.likesDisabled).toBe(false)
  expect(resp.data.addPost.sharingDisabled).toBe(true)
  expect(resp.data.addPost.verificationHidden).toBe(true)

  // change the user-level mental health setting defaults
  variables = {commentsDisabled: false, likesDisabled: true, sharingDisabled: false, verificationHidden: false}
  resp = await ourClient.mutate({mutation: mutations.setUserMentalHealthSettings, variables})
  expect(resp.data.setUserDetails.userId).toBe(ourUserId)
  expect(resp.data.setUserDetails.commentsDisabled).toBe(false)
  expect(resp.data.setUserDetails.likesDisabled).toBe(true)
  expect(resp.data.setUserDetails.sharingDisabled).toBe(false)
  expect(resp.data.setUserDetails.verificationHidden).toBe(false)

  // check those new user-level settings are used as defaults for a new post
  variables = {postId: uuidv4()}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(variables.postId)
  expect(resp.data.addPost.commentsDisabled).toBe(false)
  expect(resp.data.addPost.likesDisabled).toBe(true)
  expect(resp.data.addPost.sharingDisabled).toBe(false)
  expect(resp.data.addPost.verificationHidden).toBe(false)
})

test('Mental health settings specify values', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()

  // create a post, specify defaults
  let postId = uuidv4()
  let variables = {
    postId,
    commentsDisabled: false,
    likesDisabled: true,
    sharingDisabled: false,
    verificationHidden: false,
  }
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.commentsDisabled).toBe(false)
  expect(resp.data.addPost.likesDisabled).toBe(true)
  expect(resp.data.addPost.sharingDisabled).toBe(false)
  expect(resp.data.addPost.verificationHidden).toBe(false)

  // double check those values stuck
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.commentsDisabled).toBe(false)
  expect(resp.data.post.likesDisabled).toBe(true)
  expect(resp.data.post.sharingDisabled).toBe(false)
  expect(resp.data.post.verificationHidden).toBe(false)

  // create a post, specify opposite of defaults
  postId = uuidv4()
  variables = {
    postId,
    commentsDisabled: true,
    likesDisabled: false,
    sharingDisabled: true,
    verificationHidden: true,
  }
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.commentsDisabled).toBe(true)
  expect(resp.data.addPost.likesDisabled).toBe(false)
  expect(resp.data.addPost.sharingDisabled).toBe(true)
  expect(resp.data.addPost.verificationHidden).toBe(true)

  // double check those values stuck
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.commentsDisabled).toBe(true)
  expect(resp.data.post.likesDisabled).toBe(false)
  expect(resp.data.post.sharingDisabled).toBe(true)
  expect(resp.data.post.verificationHidden).toBe(true)
})

test('Disabled user cannot add a post', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()

  // we disable ourselves
  let resp = await ourClient.mutate({mutation: mutations.disableUser})
  expect(resp.data.disableUser.userId).toBe(ourUserId)
  expect(resp.data.disableUser.userStatus).toBe('DISABLED')

  // verify we can't add a post
  await expect(
    ourClient.mutate({mutation: mutations.addPost, variables: {postId: uuidv4(), imageData}}),
  ).rejects.toThrow(/ClientError: User .* is not ACTIVE/)
})

test('Anonymous user cannot add a post', async () => {
  ;({client: anonClient} = await cognito.getAnonymousAppSyncLogin())
  await expect(
    anonClient.mutate({mutation: mutations.addPost, variables: {postId: uuidv4(), imageData}}),
  ).rejects.toThrow(/ClientError: User .* is not ACTIVE/)
})

test('Add post with keywords attribute', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()

  const postId = uuidv4()
  const keywords = ['mine', 'bird', 'tea']
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId, imageData, keywords}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId)
      expect(post.postType).toBe('IMAGE')
      expect(post.postStatus).toBe('COMPLETED')
      expect(post.expiresAt).toBeNull()
      expect(post.originalPost.postId).toBe(postId)
      expect(post.keywords.sort()).toEqual(keywords.sort())
    })

  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postId).toBe(postId)
    expect(data.post.postType).toBe('IMAGE')
    expect(data.post.postStatus).toBe('COMPLETED')
    expect(data.post.expiresAt).toBeNull()
    expect(data.post.originalPost.postId).toBe(postId)
    expect(data.post.keywords.sort()).toEqual(keywords.sort())
  })
})
