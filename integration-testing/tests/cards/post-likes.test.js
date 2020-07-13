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

test('PostViews card generation and format', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'}})
    .then(({data}) => expect(data.addPost.postId).toBe(postId))

  // they onymously like the post
  await theirClient
    .mutate({mutation: mutations.onymouslyLikePost, variables: {postId}})
    .then(({data}) => expect(data.onymouslyLikePost.likeStatus).toBe('ONYMOUSLY_LIKED'))

  // verify a card was generated, check format
  await misc.sleep(2000)
  const cardId = await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    let card = data.self.cards.items[0]
    expect(card.cardId).toBeTruthy()
    expect(card.title).toBe('You have new likes')
    expect(card.subTitle).toBeNull()
    expect(card.action).toMatch(RegExp('^https://real.app/user/.*/post/.*/likes'))
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
    return card.cardId
  })

  // we dismiss the card
  await ourClient
    .mutate({mutation: mutations.deleteCard, variables: {cardId}})
    .then(({data}) => expect(data.deleteCard.cardId).toBe(cardId))

  // verify a card is really gone
  await misc.sleep(2000)
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(0)
    expect(data.self.cards.items).toHaveLength(0)
  })

  // we anonymously like the post
  await ourClient
    .mutate({mutation: mutations.anonymouslyLikePost, variables: {postId}})
    .then(({data}) => expect(data.anonymouslyLikePost.likeStatus).toBe('ANONYMOUSLY_LIKED'))

  // verify a card was generated, check format
  await misc.sleep(2000)
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    expect(data.self.cards.items[0].cardId).toBeTruthy()
    expect(data.self.cards.items[0].action).toMatch(RegExp('^https://real.app/user/.*/post/.*/likes'))
  })
})
