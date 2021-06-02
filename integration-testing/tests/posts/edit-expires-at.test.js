import dayjs from 'dayjs'
import duration from 'dayjs/plugin/duration'
import {v4 as uuidv4} from 'uuid'

import {cognito, eventually, generateRandomJpeg} from '../../utils'
import {mutations, queries} from '../../schema'

dayjs.extend(duration)
const imageBytes = generateRandomJpeg(8, 8)
const imageData = new Buffer.from(imageBytes).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()
const errorPolicy = 'all'

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Cant edit Post.expiresAt for post that do not exist', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const variables = {
    postId: uuidv4(),
    expiresAt: dayjs().add(dayjs.duration('P1D')).toISOString(),
  }
  await ourClient.mutate({mutation: mutations.editPostExpiresAt, variables, errorPolicy}).then(({errors}) => {
    expect(errors).toHaveLength(1)
    expect(errors[0].message).toMatch(/ClientError: Post .* does not exist/)
  })
})

test('Cant edit Post.expiresAt for post that isnt ours', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // they add a post
  let variables = {postId, imageData}
  let resp = await theirClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId)

  // we try to edit its expiresAt
  variables = {postId, expiresAt: dayjs().add(dayjs.duration('P1D')).toISOString()}
  await ourClient.mutate({mutation: mutations.editPostExpiresAt, variables, errorPolicy}).then(({errors}) => {
    expect(errors).toHaveLength(1)
    expect(errors[0].message).toMatch(/ClientError: Cannot edit another /)
  })
})

test('Cant set Post.expiresAt to datetime in the past', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // we add a post
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId)

  // we try to edit its expiresAt to a date in the past
  variables = {postId, expiresAt: dayjs().subtract(dayjs.duration('PT1M')).toISOString()}
  await ourClient.mutate({mutation: mutations.editPostExpiresAt, variables, errorPolicy}).then(({errors}) => {
    expect(errors).toHaveLength(1)
    expect(errors[0].message).toMatch(/ClientError: Cannot .* in the past/)
  })
})

test('Cant edit Post.expiresAt if we are disabled', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // we add a post
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId)

  // we disable ourselves
  resp = await ourClient.mutate({mutation: mutations.disableUser})
  expect(resp.data.disableUser.userId).toBe(ourUserId)
  expect(resp.data.disableUser.userStatus).toBe('DISABLED')

  // verify we can't edit the expires at
  variables = {postId, expiresAt: dayjs().add(dayjs.duration('P1D')).toISOString()}
  await ourClient.mutate({mutation: mutations.editPostExpiresAt, variables, errorPolicy}).then(({errors}) => {
    expect(errors).toHaveLength(1)
    expect(errors[0].message).toMatch(/ClientError: User .* is not ACTIVE/)
  })
})

test('Cant set Post.expiresAt with datetime without timezone info', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // we add a post
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId)

  // we try to edit its expiresAt to a date in the past, gql schema catches this error not our server code
  variables = {postId, expiresAt: '2019-01-01T01:01:01'}
  await ourClient.mutate({mutation: mutations.editPostExpiresAt, variables, errorPolicy}).then(({errors}) => {
    expect(errors).toHaveLength(1)
    expect(errors[0].message).toMatch("Variable 'expiresAt' has an invalid value.")
  })
})

test('Add and remove expiresAt from a Post', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // we add a post without an expiresAt
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.expiresAt).toBeNull()

  // we edit the post to give it an expiresAt
  const expiresAt = dayjs().add(dayjs.duration('P1D'))
  variables = {postId, expiresAt: expiresAt.toISOString()}
  resp = await ourClient.mutate({mutation: mutations.editPostExpiresAt, variables})
  expect(resp.data.editPostExpiresAt.postId).toBe(postId)
  expect(resp.data.editPostExpiresAt.expiresAt).toBeTruthy()
  expect(dayjs(resp.data.editPostExpiresAt.expiresAt).isSame(expiresAt)).toBe(true)

  // we edit the post to remove its expiresAt using null
  variables = {postId, expiresAt: null}
  resp = await ourClient.mutate({mutation: mutations.editPostExpiresAt, variables})
  expect(resp.data.editPostExpiresAt.postId).toBe(postId)
  expect(resp.data.editPostExpiresAt.expiresAt).toBeNull()

  // we edit the post again to give it an expiresAt
  variables = {postId, expiresAt: expiresAt.toISOString()}
  resp = await ourClient.mutate({mutation: mutations.editPostExpiresAt, variables})
  expect(resp.data.editPostExpiresAt.postId).toBe(postId)
  expect(resp.data.editPostExpiresAt.expiresAt).toBeTruthy()
  expect(dayjs(resp.data.editPostExpiresAt.expiresAt).isSame(expiresAt)).toBe(true)

  // we edit the post to remove its expiresAt using undefined
  variables = {postId}
  resp = await ourClient.mutate({mutation: mutations.editPostExpiresAt, variables})
  expect(resp.data.editPostExpiresAt.postId).toBe(postId)
  expect(resp.data.editPostExpiresAt.expiresAt).toBeNull()
})

test('Edit Post.expiresAt with UTC', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const postId = uuidv4()
  const lifetime = 'P1D'

  // add a post with a lifetime
  let variables = {postId, imageData, lifetime}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  let post = resp.data.addPost
  expect(post.postId).toBe(postId)
  expect(post.expiresAt).toBeTruthy()
  const at = dayjs(post.expiresAt)

  // change the expiresAt
  at.add(dayjs.duration(lifetime))
  const expiresAt = at.toISOString()
  resp = await ourClient.mutate({mutation: mutations.editPostExpiresAt, variables: {postId, expiresAt}})
  post = resp.data.editPostExpiresAt
  expect(post.postId).toBe(postId)
  expect(post.expiresAt).toBeTruthy()
  expect(dayjs(post.expiresAt).isSame(at)).toBe(true)

  // pull the post again to make sure that new value stuck in DB
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  post = resp.data.post
  expect(post.postId).toBe(postId)
  expect(post.expiresAt).toBeTruthy()
  expect(dayjs(post.expiresAt).isSame(at)).toBe(true)
})

test('Edit Post.expiresAt with non-UTC', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const postId = uuidv4()
  const lifetime = 'P1D'

  // add a post with a lifetime
  let variables = {postId, imageData, lifetime}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  let post = resp.data.addPost
  expect(post.postId).toBe(postId)
  expect(post.expiresAt).toBeTruthy()

  // change the expiresAt
  const expiresAtUtc = dayjs(post.expiresAt).add(dayjs.duration(lifetime))
  const expiresAt = expiresAtUtc.toISOString().replace('Z', '+01:30')
  const expectedExpiresAt = expiresAtUtc.subtract(dayjs.duration('PT1H30M')) // account for the timezone offset

  resp = await ourClient.mutate({mutation: mutations.editPostExpiresAt, variables: {postId, expiresAt}})
  post = resp.data.editPostExpiresAt
  expect(post.postId).toBe(postId)
  expect(post.expiresAt).toBeTruthy()
  expect(dayjs(post.expiresAt).isSame(expectedExpiresAt)).toBe(true)

  // pull the post again to make sure that new value stuck in DB
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  post = resp.data.post
  expect(post.postId).toBe(postId)
  expect(post.expiresAt).toBeTruthy()
  expect(dayjs(post.expiresAt).isSame(expectedExpiresAt)).toBe(true)
})

test('Adding and clearing Post.expiresAt removes and adds it to users stories', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // add a post with no lifetime
  let variables = {postId, imageData}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.expiresAt).toBeNull()

  // check we start with no stories
  resp = await ourClient.query({query: queries.userStories, variables: {userId: ourUserId}})
  expect(resp.data.user.stories.items).toHaveLength(0)

  // set the post's expiresAt, changing it to a story
  const expiresAt = dayjs().add(dayjs.duration('PT1H')).toISOString()
  resp = await ourClient.mutate({mutation: mutations.editPostExpiresAt, variables: {postId, expiresAt}})
  expect(resp.data.editPostExpiresAt.postId).toBe(postId)
  expect(resp.data.editPostExpiresAt.expiresAt).toBeTruthy()

  // check we now have a story
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.userStories, variables: {userId: ourUserId}})
    expect(data.user.stories.items).toHaveLength(1)
    expect(data.user.stories.items[0].postId).toBe(postId)
  })

  // remove the post's expiresAt, changing it to not be a story
  resp = await ourClient.mutate({mutation: mutations.editPostExpiresAt, variables: {postId}})
  expect(resp.data.editPostExpiresAt.postId).toBe(postId)
  expect(resp.data.editPostExpiresAt.expiresAt).toBeNull()

  // check no longer have a story
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.userStories, variables: {userId: ourUserId}})
    expect(data.user.stories.items).toHaveLength(0)
  })
})

test('Clearing Post.expiresAt removes from first followed stories', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // we follow them
  let resp = await ourClient.mutate({mutation: mutations.followUser, variables: {userId: theirUserId}})
  expect(resp.data.followUser.followedStatus).toBe('FOLLOWING')

  // they add a post that is also a story
  let variables = {postId, imageData, lifetime: 'PT1H'}
  resp = await theirClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.expiresAt).toBeTruthy()

  // check we see them in our first followed stories
  resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.followedUsersWithStories.items).toHaveLength(1)
  expect(resp.data.self.followedUsersWithStories.items[0].userId).toBe(theirUserId)

  // they edit that post so it is no longer a story
  variables = {postId, expiresAt: null}
  resp = await theirClient.mutate({mutation: mutations.editPostExpiresAt, variables})
  expect(resp.data.editPostExpiresAt.postId).toBe(postId)
  expect(resp.data.editPostExpiresAt.expiresAt).toBeNull()

  // check that is reflected in our first followed stories
  resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.followedUsersWithStories.items).toHaveLength(0)
})

test('Changing Post.expiresAt is reflected in first followed stories', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()
  const {client: otherClient, userId: otherUserId} = await loginCache.getCleanLogin()
  const theirPostId = uuidv4()
  const otherPostId = uuidv4()

  // we follow them
  let resp = await ourClient.mutate({mutation: mutations.followUser, variables: {userId: theirUserId}})
  expect(resp.data.followUser.followedStatus).toBe('FOLLOWING')

  // we follow other
  resp = await ourClient.mutate({mutation: mutations.followUser, variables: {userId: otherUserId}})
  expect(resp.data.followUser.followedStatus).toBe('FOLLOWING')

  // let those following relationships settle
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.followedsCount).toBe(2)
  })

  // they add a post that is also a story
  let variables = {postId: theirPostId, imageData, lifetime: 'PT1H'}
  resp = await theirClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(theirPostId)
  expect(resp.data.addPost.expiresAt).toBeTruthy()
  const expiresAt = dayjs(resp.data.addPost.expiresAt)

  // other adds a post that is also a story
  variables = {postId: otherPostId, imageData, lifetime: 'PT2H'}
  resp = await otherClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(otherPostId)
  expect(resp.data.addPost.expiresAt).toBeTruthy()

  // check we see them as expected in our first followed stories
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.followedUsersWithStories.items).toHaveLength(2)
    expect(data.self.followedUsersWithStories.items[0].userId).toBe(theirUserId)
    expect(data.self.followedUsersWithStories.items[1].userId).toBe(otherUserId)
  })

  // edit their post's expiration date to a date further in the future
  variables = {postId: theirPostId, expiresAt: expiresAt.add(dayjs.duration('PT2H')).toISOString()}
  resp = await theirClient.mutate({mutation: mutations.editPostExpiresAt, variables})
  expect(resp.data.editPostExpiresAt.postId).toBe(theirPostId)
  expect(resp.data.editPostExpiresAt.expiresAt).toBeTruthy()

  // check we see them as expected in our first followed stories (order reversed from earlier)
  resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.followedUsersWithStories.items).toHaveLength(2)
  expect(resp.data.self.followedUsersWithStories.items[0].userId).toBe(otherUserId)
  expect(resp.data.self.followedUsersWithStories.items[1].userId).toBe(theirUserId)

  // edit their post's expiration date to a date closer in the future
  variables = {postId: theirPostId, expiresAt: expiresAt.toISOString()}
  resp = await theirClient.mutate({mutation: mutations.editPostExpiresAt, variables})
  expect(resp.data.editPostExpiresAt.postId).toBe(theirPostId)
  expect(resp.data.editPostExpiresAt.expiresAt).toBeTruthy()

  // check we see them as expected in our first followed stories (order back to original)
  resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.followedUsersWithStories.items).toHaveLength(2)
  expect(resp.data.self.followedUsersWithStories.items[0].userId).toBe(theirUserId)
  expect(resp.data.self.followedUsersWithStories.items[1].userId).toBe(otherUserId)
})
