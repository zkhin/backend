const {v4: uuidv4} = require('uuid')

const {cognito, deleteDefaultCard, eventually} = require('../../utils')
const {mutations, queries} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Cards are private to user themselves', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()
  await deleteDefaultCard(ourClient)

  // verify we see our zero cards and count on self
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(0)
    expect(data.self.cards.items).toHaveLength(0)
  })

  // verify we see our zero cards and count on user
  await ourClient.query({query: queries.user, variables: {userId: ourUserId}}).then(({data: {user}}) => {
    expect(user.userId).toBe(ourUserId)
    expect(user.cardCount).toBe(0)
    expect(user.cards.items).toHaveLength(0)
  })

  // verify they don't see our zero cards and count
  await theirClient.query({query: queries.user, variables: {userId: ourUserId}}).then(({data: {user}}) => {
    expect(user.userId).toBe(ourUserId)
    expect(user.cardCount).toBeNull()
    expect(user.cards).toBeNull()
  })
})

test('List cards', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()
  await deleteDefaultCard(ourClient)

  // verify list & count for no cards
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(0)
    expect(data.self.cards.items).toHaveLength(0)
  })

  // they start a direct chat with us
  const chatId = uuidv4()
  let variables = {userId: ourUserId, chatId, messageId: uuidv4(), messageText: 'lore ipsum'}
  await theirClient
    .mutate({mutation: mutations.createDirectChat, variables})
    .then(({data}) => expect(data.createDirectChat.chatId).toBe(chatId))

  // verify list & count that one card
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
  })

  // we add a post
  const postId = uuidv4()
  variables = {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'}
  await ourClient.mutate({mutation: mutations.addPost, variables}).then(({data: {addPost}}) => {
    expect(addPost.postId).toBe(postId)
  })

  // they comment on our post
  variables = {commentId: uuidv4(), postId, text: 'nice post'}
  await theirClient.mutate({mutation: mutations.addComment, variables})

  // verify list & count for those two cards, including order (most recent first)
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(2)
    expect(data.self.cards.items).toHaveLength(2)
    expect(data.self.cards.items[0].action).toContain('https://real.app/')
    expect(data.self.cards.items[1].action).toContain('https://real.app/')
  })
})

test('Delete card, generate new card after deleting', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()
  await deleteDefaultCard(ourClient)

  // verify can't delete card that doesn't exist
  await ourClient
    .mutate({mutation: mutations.deleteCard, variables: {cardId: uuidv4()}, errorPolicy: 'all'})
    .then(({errors}) => {
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toMatch(/ClientError: No card .* found/)
    })

  // they start a direct chat with us, verify generates us a card
  const chatId = uuidv4()
  await theirClient
    .mutate({
      mutation: mutations.createDirectChat,
      variables: {userId: ourUserId, chatId, messageId: uuidv4(), messageText: 'lore ipsum'},
    })
    .then(({data}) => expect(data.createDirectChat.chatId).toBe(chatId))
  const card = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    expect(data.self.cards.items[0].cardId).toBeTruthy()
    return data.self.cards.items[0]
  })

  // verify they can't delete our card
  await theirClient
    .mutate({mutation: mutations.deleteCard, variables: {cardId: card.cardId}, errorPolicy: 'all'})
    .then(({errors}) => {
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toMatch(/ClientError: Caller.* does not own Card /)
    })

  // verify we can delete our card
  await ourClient
    .mutate({mutation: mutations.deleteCard, variables: {cardId: card.cardId}})
    .then(({data}) => expect(data.deleteCard).toEqual(card))
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(0)
    expect(data.self.cards.items).toHaveLength(0)
  })

  // they add a message to a chat that already has new messages - verify no new card generated
  await theirClient
    .mutate({mutation: mutations.addChatMessage, variables: {chatId, messageId: uuidv4(), text: 'lore ipsum'}})
    .then(({data}) => expect(data.addChatMessage.messageId).toBeTruthy())
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(0)
    expect(data.self.cards.items).toHaveLength(0)
  })

  // they open up a group chat with us, verify card generated same as old one with a different title
  await theirClient
    .mutate({
      mutation: mutations.createGroupChat,
      variables: {chatId: uuidv4(), userIds: [ourUserId], messageId: uuidv4(), messageText: 'm1'},
    })
    .then(({data}) => expect(data.createGroupChat.chatId).toBeTruthy())
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    expect(data.self.cards.items[0].cardId).toBe(card.cardId)
    expect(data.self.cards.items[0].title).not.toBe(card.title)
  })
})
