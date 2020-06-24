/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito')
const misc = require('../../utils/misc')
const {mutations, queries} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Generate comment card', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let resp = await ourClient.mutate({
    mutation: mutations.addPost,
    variables: {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'},
  })
  expect(resp.data.addPost.postId).toBe(postId)

  // we comment on our post
  resp = await ourClient.mutate({
    mutation: mutations.addComment,
    variables: {commentId: uuidv4(), postId, text: 'nice post'},
  })

  // verify no card generated for our comment
  await misc.sleep(1000)
  resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(0)
  expect(resp.data.self.cards.items).toHaveLength(0)

  // they comment on our post
  const commentId = uuidv4()
  resp = await theirClient.mutate({
    mutation: mutations.addComment,
    variables: {commentId, postId, text: 'nice post'},
  })
  expect(resp.data.addComment.commentId).toBe(commentId)

  // verify a card was generated for their comment
  await misc.sleep(1000)
  resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(1)
  expect(resp.data.self.cards.items).toHaveLength(1)

  // verify that card has expected format
  let card = resp.data.self.cards.items[0]
  expect(card.cardId).toBeTruthy()
  expect(card.title).toBe('You have new comments')
  expect(card.subTitle).toBeNull()
  expect(card.action).toMatch(RegExp('^https://real.app/chat/post/'))
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

  // they comment again on the post
  resp = await theirClient.mutate({
    mutation: mutations.addComment,
    variables: {commentId: uuidv4(), postId, text: 'nice post'},
  })

  // verify we still have just one card
  await misc.sleep(1000)
  resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(1)
  expect(resp.data.self.cards.items).toHaveLength(1)

  // we view that post
  resp = await ourClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId]}})

  // verify the card has disappeared
  await misc.sleep(1000)
  resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(0)
  expect(resp.data.self.cards.items).toHaveLength(0)
})

test('Comment cards are post-specific', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add two posts
  const [postId1, postId2] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({
    mutation: mutations.addPost,
    variables: {postId: postId1, postType: 'TEXT_ONLY', text: 'lore ipsum'},
  })
  expect(resp.data.addPost.postId).toBe(postId1)
  resp = await ourClient.mutate({
    mutation: mutations.addPost,
    variables: {postId: postId2, postType: 'TEXT_ONLY', text: 'lore ipsum'},
  })
  expect(resp.data.addPost.postId).toBe(postId2)

  // they comment on our first post
  const commentId1 = uuidv4()
  resp = await theirClient.mutate({
    mutation: mutations.addComment,
    variables: {commentId: commentId1, postId: postId1, text: 'nice post'},
  })
  expect(resp.data.addComment.commentId).toBe(commentId1)

  // verify a card was generated for their comment
  await misc.sleep(1000)
  resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(1)
  expect(resp.data.self.cards.items).toHaveLength(1)
  expect(resp.data.self.cards.items[0].action).toContain(postId1)
  const cardId1 = resp.data.self.cards.items[0].cardId

  // they comment on our second post
  const commentId2 = uuidv4()
  resp = await theirClient.mutate({
    mutation: mutations.addComment,
    variables: {commentId: commentId2, postId: postId2, text: 'nice post'},
  })
  expect(resp.data.addComment.commentId).toBe(commentId2)

  // verify a second card was generated
  await misc.sleep(1000)
  resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(2)
  expect(resp.data.self.cards.items).toHaveLength(2)
  expect(resp.data.self.cards.items[1].cardId).toBe(cardId1)
  expect(resp.data.self.cards.items[0].action).toContain(postId2)
  const cardId2 = resp.data.self.cards.items[0].cardId

  // they add another comment on our first post
  const commentId3 = uuidv4()
  resp = await theirClient.mutate({
    mutation: mutations.addComment,
    variables: {commentId: commentId3, postId: postId1, text: 'nice post'},
  })
  expect(resp.data.addComment.commentId).toBe(commentId3)

  // verify a second card was generated
  await misc.sleep(1000)
  resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(2)
  expect(resp.data.self.cards.items).toHaveLength(2)
  expect(resp.data.self.cards.items[1].cardId).toBe(cardId1)
  expect(resp.data.self.cards.items[0].cardId).toBe(cardId2)

  // we view first post
  resp = await ourClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId1]}})

  // verify that card has disappeared, the other remains
  await misc.sleep(1000)
  resp = await ourClient.query({query: queries.self})
  expect(resp.data.self.userId).toBe(ourUserId)
  expect(resp.data.self.cardCount).toBe(1)
  expect(resp.data.self.cards.items).toHaveLength(1)
  expect(resp.data.self.cards.items[0].cardId).toBe(cardId2)
})
