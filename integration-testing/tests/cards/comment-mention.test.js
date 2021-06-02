import {v4 as uuidv4} from 'uuid'

import {cognito, deleteDefaultCard, eventually, generateRandomJpeg, sleep} from '../../utils'
import {mutations, queries} from '../../schema'

const imageData = generateRandomJpeg(8, 8)
const imageDataB64 = new Buffer.from(imageData).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('CommenttMention card generation and format, fullfilling and dismissing card', async () => {
  const {client: ourClient, userId: ourUserId, username: ourUsername} = await loginCache.getCleanLogin()
  const {client: theirClient, username: theirUsername} = await loginCache.getCleanLogin()
  const {client: otherClient, userId: otherUserId, username: otherUsername} = await loginCache.getCleanLogin()
  await Promise.all([ourClient, otherClient].map(deleteDefaultCard))

  // we add a post
  const postId = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId, imageData: imageDataB64}})
    .then(({data}) => expect(data.addPost.postId).toBe(postId))

  // they comment on our post and tag us and other
  const commentId = uuidv4()
  const text = `hey @${ourUsername} and @${otherUsername}, como va?`
  await theirClient
    .mutate({mutation: mutations.addComment, variables: {commentId, postId, text}})
    .then(({data}) => expect(data.addComment.commentId).toBe(commentId))

  // verify a card was generated for us, check format
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(2) // one of these is for the comment, another is for the mention
    expect(data.self.cards.items).toHaveLength(2)
    const cards = data.self.cards.items
    const card = cards[0].cardId.includes('COMMENT_MENTION') ? cards[0] : cards[1]
    expect(card.cardId).toBeTruthy()
    expect(card.title).toMatch(RegExp('^@.* mentioned you in a comment'))
    expect(card.title).toContain(theirUsername)
    expect(card.subTitle).toBeNull()
    expect(card.action).toMatch(RegExp('^https://real.app/user/.*/post/.*/comments/.*'))
    expect(card.action).toContain(ourUserId)
    expect(card.action).toContain(postId)
    expect(card.action).toContain(commentId)
    expect(card.thumbnail).toBeTruthy() // we get the post's thumbnail here
  })

  // verify a card was generated for other, check format
  const cardId2 = await otherClient.query({query: queries.self}).then(({data: {self: user}}) => {
    expect(user.userId).toBe(otherUserId)
    expect(user.cardCount).toBe(1)
    expect(user.cards.items).toHaveLength(1)
    let card = user.cards.items[0]
    expect(card.cardId).toBeTruthy()
    expect(card.title).toMatch(RegExp('^@.* mentioned you in a comment'))
    expect(card.title).toContain(theirUsername)
    expect(card.subTitle).toBeNull()
    expect(card.action).toMatch(RegExp('^https://real.app/user/.*/post/.*/comments/.*'))
    expect(card.action).toContain(ourUserId)
    expect(card.action).toContain(postId)
    expect(card.action).toContain(commentId)
    expect(card.thumbnail).toBeTruthy() // we get the post's thumbnail here
    return card.cardId
  })

  // they view the post, verify no change to cards
  await theirClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId]}})
  await sleep()
  await ourClient.query({query: queries.self}).then(({data}) => expect(data.self.cardCount).toBe(2))
  await otherClient.query({query: queries.self}).then(({data}) => expect(data.self.cardCount).toBe(1))

  // other dismisses their card, verify gone
  await otherClient
    .mutate({mutation: mutations.deleteCard, variables: {cardId: cardId2}})
    .then(({data}) => expect(data.deleteCard.cardId).toBe(cardId2))
  await eventually(async () => {
    const {data} = await otherClient.query({query: queries.self})
    expect(data.self.cardCount).toBe(0)
  })

  // we view the post, verify both our cards disappear
  await ourClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId]}})
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.cardCount).toBe(0)
  })
})

test('CommenttMention card deletion on comment deletion', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: other1Client, username: other1Username} = await loginCache.getCleanLogin()
  const {client: other2Client, username: other2Username} = await loginCache.getCleanLogin()
  await Promise.all([other1Client, other2Client].map(deleteDefaultCard))

  // we add a text-only post
  const postId = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'}})
    .then(({data}) => expect(data.addPost.postId).toBe(postId))

  // we comment on the post, tagging the other users
  const commentId = uuidv4()
  const text = `hey @${other1Username} and @${other2Username}, como va?`
  await ourClient
    .mutate({mutation: mutations.addComment, variables: {commentId, postId, text}})
    .then(({data}) => expect(data.addComment.commentId).toBe(commentId))

  // verify both users see cards
  await eventually(async () => {
    const {data} = await other1Client.query({query: queries.self})
    expect(data.self.cardCount).toBe(1)
  })
  await eventually(async () => {
    const {data} = await other2Client.query({query: queries.self})
    expect(data.self.cardCount).toBe(1)
  })

  // we delete the comment
  await ourClient
    .mutate({mutation: mutations.deleteComment, variables: {commentId}})
    .then(({data}) => expect(data.deleteComment.commentId).toBe(commentId))

  // verify both cards have disappeared
  await eventually(async () => {
    const {data} = await other1Client.query({query: queries.self})
    expect(data.self.cardCount).toBe(0)
  })
  await eventually(async () => {
    const {data} = await other2Client.query({query: queries.self})
    expect(data.self.cardCount).toBe(0)
  })
})
