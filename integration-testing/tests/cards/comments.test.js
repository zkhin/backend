/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito')
const misc = require('../../utils/misc')
const {mutations, queries, subscriptions} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Comment card format, subscription notifications', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we subscribe to our cards
  const [resolvers, rejectors] = [[], []]
  const sub = await ourClient
    .subscribe({query: subscriptions.onCardNotification, variables: {userId: ourUserId}})
    .subscribe({
      next: (resp) => {
        rejectors.pop()
        resolvers.pop()(resp)
      },
      error: (resp) => {
        resolvers.pop()
        rejectors.pop()(resp)
      },
    })
  const subInitTimeout = misc.sleep(15000) // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541
  await misc.sleep(2000) // let the subscription initialize
  let nextNotification = new Promise((resolve, reject) => {
    resolvers.push(resolve)
    rejectors.push(reject)
  })

  // we add a post
  const postId = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'}})
    .then(({data}) => expect(data.addPost.postId).toBe(postId))

  // we comment on our post
  await ourClient
    .mutate({mutation: mutations.addComment, variables: {commentId: uuidv4(), postId, text: 'nice post'}})
    .then(({data}) => expect(data.addComment.commentId).toBeTruthy())

  // verify no card generated for our comment
  await misc.sleep(1000)
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(0)
    expect(data.self.cards.items).toHaveLength(0)
  })

  // they comment on our post
  await theirClient
    .mutate({mutation: mutations.addComment, variables: {commentId: uuidv4(), postId, text: 'nice post'}})
    .then(({data}) => expect(data.addComment.commentId).toBeTruthy())

  // verify a card was generated for their comment, check format
  await misc.sleep(1000)
  const card1 = await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    let card = data.self.cards.items[0]
    expect(card.cardId).toBeTruthy()
    expect(card.title).toBe('You have 1 new comment')
    expect(card.subTitle).toBeNull()
    expect(card.action).toMatch(RegExp('^https://real.app/user/.*/post/.*/comments$'))
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
    return card
  })

  // verify subscription fired correctly with that new card
  // Note that thumbnails are not included in subscription notifcations, yet
  await nextNotification.then(({data}) => {
    expect(data.onCardNotification.userId).toBe(ourUserId)
    expect(data.onCardNotification.type).toBe('ADDED')
    const {thumbnail: cardNotificationThumbnail, ...cardNotificationOtherFields} = data.onCardNotification.card
    const {thumbnail: card1Thumbnail, ...card1OtherFields} = card1
    expect(cardNotificationThumbnail).toBeNull()
    expect(cardNotificationThumbnail).not.toEqual(card1Thumbnail)
    expect(cardNotificationOtherFields).toEqual(card1OtherFields)
  })
  nextNotification = new Promise((resolve, reject) => {
    resolvers.push(resolve)
    rejectors.push(reject)
  })

  // they comment again on the post
  await theirClient
    .mutate({mutation: mutations.addComment, variables: {commentId: uuidv4(), postId, text: 'nice post'}})
    .then(({data}) => expect(data.addComment.commentId).toBeTruthy())

  // verify card has changed title and possibly thumbnail urls, but nothing else
  await misc.sleep(1000)
  const card2 = await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    const card = data.self.cards.items[0]
    expect(card.title).toBe('You have 2 new comments')
    const {title: cardTitle, thumbnail: cardThumbnail, ...cardOtherFields} = card
    const {title: card1Title, thumbnail: card1Thumbnail, ...card1OtherFields} = card1
    expect(cardTitle).not.toBe(card1Title)
    expect(cardThumbnail).not.toEqual(card1Thumbnail)
    expect(cardOtherFields).toEqual(card1OtherFields)
    return card
  })

  // verify subscription fired correctly with that changed card
  await nextNotification.then(({data}) => {
    expect(data.onCardNotification.userId).toBe(ourUserId)
    expect(data.onCardNotification.type).toBe('EDITED')
    const {thumbnail: cardNotificationThumbnail, ...cardNotificationOtherFields} = data.onCardNotification.card
    const {thumbnail: card2Thumbnail, ...card2OtherFields} = card2
    expect(cardNotificationThumbnail).toBeNull()
    expect(cardNotificationThumbnail).not.toEqual(card2Thumbnail)
    expect(cardNotificationOtherFields).toEqual(card2OtherFields)
  })
  nextNotification = new Promise((resolve, reject) => {
    resolvers.push(resolve)
    rejectors.push(reject)
  })

  // we view that post
  await ourClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId]}})

  // verify the card has disappeared
  await misc.sleep(1000)
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(0)
    expect(data.self.cards.items).toHaveLength(0)
  })

  // verify subscription fired correctly for card deletion
  await nextNotification.then(({data}) => {
    expect(data.onCardNotification.userId).toBe(ourUserId)
    expect(data.onCardNotification.type).toBe('DELETED')
    const {thumbnail: cardNotificationThumbnail, ...cardNotificationOtherFields} = data.onCardNotification.card
    const {thumbnail: card2Thumbnail, ...card2OtherFields} = card2
    expect(cardNotificationThumbnail).toBeNull()
    expect(cardNotificationThumbnail).not.toEqual(card2Thumbnail)
    expect(cardNotificationOtherFields).toEqual(card2OtherFields)
  })

  // shut down the subscription
  sub.unsubscribe()
  await subInitTimeout
})

test('Comment cards are post-specific', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add two posts
  const [postId1, postId2] = [uuidv4(), uuidv4()]
  await ourClient
    .mutate({
      mutation: mutations.addPost,
      variables: {postId: postId1, postType: 'TEXT_ONLY', text: 'lore ipsum'},
    })
    .then(({data}) => expect(data.addPost.postId).toBe(postId1))
  await ourClient
    .mutate({
      mutation: mutations.addPost,
      variables: {postId: postId2, postType: 'TEXT_ONLY', text: 'lore ipsum'},
    })
    .then(({data}) => expect(data.addPost.postId).toBe(postId2))

  // they comment on our first post
  await theirClient
    .mutate({
      mutation: mutations.addComment,
      variables: {commentId: uuidv4(), postId: postId1, text: 'nice post'},
    })
    .then(({data}) => expect(data.addComment.commentId).toBeTruthy())

  // verify a card was generated for their comment
  await misc.sleep(1000)
  const cardId1 = await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    expect(data.self.cards.items[0].action).toContain(postId1)
    return data.self.cards.items[0].cardId
  })

  // they comment on our second post
  await theirClient
    .mutate({
      mutation: mutations.addComment,
      variables: {commentId: uuidv4(), postId: postId2, text: 'nice post'},
    })
    .then(({data}) => expect(data.addComment.commentId).toBeTruthy())

  // verify a second card was generated
  await misc.sleep(1000)
  const cardId2 = await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(2)
    expect(data.self.cards.items).toHaveLength(2)
    expect(data.self.cards.items[1].cardId).toBe(cardId1)
    expect(data.self.cards.items[0].action).toContain(postId2)
    return data.self.cards.items[0].cardId
  })

  // they add another comment on our first post
  await theirClient
    .mutate({
      mutation: mutations.addComment,
      variables: {commentId: uuidv4(), postId: postId1, text: 'nice post'},
    })
    .then(({data}) => expect(data.addComment.commentId).toBeTruthy())

  // verify a second card was generated
  await misc.sleep(1000)
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(2)
    expect(data.self.cards.items).toHaveLength(2)
    expect(data.self.cards.items[1].cardId).toBe(cardId1)
    expect(data.self.cards.items[0].cardId).toBe(cardId2)
  })

  // we view first post
  await ourClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId1]}})

  // verify that card has disappeared, the other remains
  await misc.sleep(1000)
  await ourClient.query({query: queries.self}).then(({data}) => {
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    expect(data.self.cards.items[0].cardId).toBe(cardId2)
  })
})
