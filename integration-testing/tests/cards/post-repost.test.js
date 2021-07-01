import {v4 as uuidv4} from 'uuid'

import {cognito, deleteDefaultCard, eventually, generateRandomJpeg, sleep} from '../../utils'
import {mutations, queries} from '../../schema'

const imageData = generateRandomJpeg(8, 8)
const imageDataB64 = new Buffer.from(imageData).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('PostRepost card generation and format, fullfilling card', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId, username: theirUsername} = await loginCache.getCleanLogin()
  await deleteDefaultCard(ourClient)

  // we add an image post
  const originalPostId = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId: originalPostId, imageData: imageDataB64}})
    .then(({data}) => expect(data.addPost.postId).toBe(originalPostId))

  // let the system hash that image
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId: originalPostId}})
    expect(data.post.originalPost).toBeTruthy()
    expect(data.post.originalPost.postId).toBe(originalPostId)
  })

  // check we have no cards yet
  await ourClient.query({query: queries.self}).then(({data}) => expect(data.self.cardCount).toBe(0))

  // they add an image post, same image as ours - ie a repost
  const postId = uuidv4()
  await theirClient
    .mutate({mutation: mutations.addPost, variables: {postId, imageData: imageDataB64}})
    .then(({data}) => expect(data.addPost.postId).toBe(postId))

  // verify a card was generated for us, check format
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    let card = data.self.cards.items[0]
    expect(card.cardId).toBeTruthy()
    expect(card.title).toMatch(RegExp('^@.* reposted one of your posts'))
    expect(card.title).toContain(theirUsername)
    expect(card.subTitle).toBeNull()
    expect(card.action).toMatch(RegExp('^https://real.app/apps/social/user/.*/post/.*'))
    expect(card.action).toContain(theirUserId)
    expect(card.action).toContain(postId)
    expect(card.thumbnail).toBeTruthy()
    expect(card.thumbnail.url64p).toMatch(RegExp('^https://.*.jpg'))
    expect(card.thumbnail.url480p).toMatch(RegExp('^https://.*.jpg'))
    expect(card.thumbnail.url1080p).toMatch(RegExp('^https://.*.jpg'))
    expect(card.thumbnail.url4k).toMatch(RegExp('^https://.*.jpg'))
    expect(card.thumbnail.url).toMatch(RegExp('^https://.*.jpg'))
    expect(card.thumbnail.url64p).toContain(postId)
    expect(card.thumbnail.url480p).toContain(postId)
    expect(card.thumbnail.url1080p).toContain(postId)
    expect(card.thumbnail.url4k).toContain(postId)
    expect(card.thumbnail.url).toContain(postId)
  })

  // we view our post, verify no change to cards
  await ourClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [originalPostId]}})
  await sleep()
  await ourClient.query({query: queries.self}).then(({data}) => expect(data.self.cardCount).toBe(1))

  // we view their post, verify card disappears
  await ourClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId]}})
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.cardCount).toBe(0)
  })
})

test('PostRepost card deleted when post deleted', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()
  await deleteDefaultCard(ourClient)

  // we add an image post
  const originalPostId = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId: originalPostId, imageData: imageDataB64}})
    .then(({data}) => expect(data.addPost.postId).toBe(originalPostId))

  // let the system hash that image
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId: originalPostId}})
    expect(data.post.originalPost).toBeTruthy()
    expect(data.post.originalPost.postId).toBe(originalPostId)
  })

  // check we have no cards yet
  await ourClient.query({query: queries.self}).then(({data}) => expect(data.self.cardCount).toBe(0))

  // they add an image post, same image as ours - ie a repost
  const postId = uuidv4()
  await theirClient
    .mutate({mutation: mutations.addPost, variables: {postId, imageData: imageDataB64}})
    .then(({data}) => expect(data.addPost.postId).toBe(postId))

  // verify a card was generated for us
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.cardCount).toBe(1)
  })

  // they delete their post
  await theirClient
    .mutate({mutation: mutations.deletePost, variables: {postId}})
    .then(({data}) => expect(data.deletePost.postId).toBe(postId))

  // verify our card disappears
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.cardCount).toBe(0)
  })
})
