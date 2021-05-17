const {v4: uuidv4} = require('uuid')

const {cognito, deleteDefaultCard, eventually, generateRandomJpeg, sleep} = require('../../utils')
const {mutations, queries, subscriptions} = require('../../schema')

const imageData = generateRandomJpeg(8, 8)
const imageDataB64 = new Buffer.from(imageData).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Comment card format, subscription notifications', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()
  await deleteDefaultCard(ourClient)

  // we subscribe to our cards
  const handlers = []
  const sub = await ourClient
    .subscribe({query: subscriptions.onCardNotification, variables: {userId: ourUserId}})
    .subscribe({
      next: ({data: {onCardNotification: notification}}) => {
        const handler = handlers.shift()
        expect(handler).toBeDefined()
        handler(notification)
      },
      error: (resp) => expect(`Subscription error: ${resp}`).toBeNull(),
    })
  const subInitTimeout = sleep('subTimeout')
  await sleep('subInit')
  let nextNotification = new Promise((resolve) => handlers.push(resolve))

  // we add a post
  const postId = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId, imageData: imageDataB64}})
    .then(({data}) => expect(data.addPost.postId).toBe(postId))

  // we comment on our post
  await ourClient
    .mutate({mutation: mutations.addComment, variables: {commentId: uuidv4(), postId, text: 'nice post'}})
    .then(({data}) => expect(data.addComment.commentId).toBeTruthy())

  // verify no card generated for our comment
  await sleep()
  await ourClient.query({query: queries.self}).then(({data: {self: user}}) => {
    expect(user.userId).toBe(ourUserId)
    expect(user.cardCount).toBe(0)
    expect(user.cards.items).toHaveLength(0)
  })

  // they comment on our post
  await theirClient
    .mutate({mutation: mutations.addComment, variables: {commentId: uuidv4(), postId, text: 'nice post'}})
    .then(({data}) => expect(data.addComment.commentId).toBeTruthy())

  // verify a card was generated for their comment, check format
  const card1 = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
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
  // Note that thumbnails are not included in subscription notifcations
  await nextNotification.then((notification) => {
    expect(notification.userId).toBe(ourUserId)
    expect(notification.type).toBe('ADDED')
    const {thumbnail, ...card1OtherFields} = card1
    expect(thumbnail).toBeTruthy()
    expect(notification.card).toEqual(card1OtherFields)
  })
  nextNotification = new Promise((resolve) => handlers.push(resolve))

  // they comment again on the post
  await theirClient
    .mutate({mutation: mutations.addComment, variables: {commentId: uuidv4(), postId, text: 'nice post'}})
    .then(({data}) => expect(data.addComment.commentId).toBeTruthy())

  // verify card has changed title, but nothing else
  const card2 = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    const card = data.self.cards.items[0]
    expect(card.title).toBe('You have 2 new comments')
    const {title: cardTitle, ...cardOtherFields} = card
    const {title: card1Title, ...card1OtherFields} = card1
    expect(cardTitle).not.toBe(card1Title)
    expect(cardOtherFields).toEqual(card1OtherFields)
    return card
  })

  // verify subscription fired correctly with that changed card
  await nextNotification.then((notification) => {
    expect(notification.userId).toBe(ourUserId)
    expect(notification.type).toBe('EDITED')
    const {thumbnail, ...card2OtherFields} = card2
    expect(thumbnail).toBeTruthy()
    expect(notification.card).toEqual(card2OtherFields)
  })
  nextNotification = new Promise((resolve) => handlers.push(resolve))

  // we view that post
  await ourClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId]}})

  // verify the card has disappeared
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(0)
    expect(data.self.cards.items).toHaveLength(0)
  })

  // verify subscription fired correctly for card deletion
  await nextNotification.then((notification) => {
    expect(notification.userId).toBe(ourUserId)
    expect(notification.type).toBe('DELETED')
    const {thumbnail, ...card2OtherFields} = card2
    expect(thumbnail).toBeTruthy()
    expect(notification.card).toEqual(card2OtherFields)
  })

  // shut down the subscription
  sub.unsubscribe()
  await subInitTimeout
})

test('Comment cards are post-specific', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()
  await deleteDefaultCard(ourClient)

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
  const cardId1 = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    expect(data.self.cards.items[0].action).toContain(postId1)
    expect(data.self.cards.items[0].thumbnail).toBeNull()
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
  const cardId2 = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(2)
    expect(data.self.cards.items).toHaveLength(2)
    expect(data.self.cards.items[1].cardId).toBe(cardId1)
    expect(data.self.cards.items[0].action).toContain(postId2)
    expect(data.self.cards.items[0].thumbnail).toBeNull()
    return data.self.cards.items[0].cardId
  })

  // they add another comment on our first post
  await theirClient
    .mutate({
      mutation: mutations.addComment,
      variables: {commentId: uuidv4(), postId: postId1, text: 'nice post'},
    })
    .then(({data}) => expect(data.addComment.commentId).toBeTruthy())

  // verify cards did not change
  await sleep()
  await ourClient.query({query: queries.self}).then(({data: {self: user}}) => {
    expect(user.userId).toBe(ourUserId)
    expect(user.cardCount).toBe(2)
    expect(user.cards.items).toHaveLength(2)
    expect(user.cards.items[1].cardId).toBe(cardId1)
    expect(user.cards.items[0].cardId).toBe(cardId2)
  })

  // we view first post
  await ourClient.mutate({mutation: mutations.reportPostViews, variables: {postIds: [postId1]}})

  // verify that card has disappeared, the other remains
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    expect(data.self.cards.items[0].cardId).toBe(cardId2)
  })
})
