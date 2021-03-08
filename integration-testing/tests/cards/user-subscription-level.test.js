const cognito = require('../../utils/cognito')
const misc = require('../../utils/misc')
const {mutations, queries} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

// https://github.com/real-social-media/promo_codes/blob/master/bucket/promo_codes.json
const promotionCode1 = 'zayar_test'
const promotionCode2 = 'ianmcLoughlin'
const promotionCode3 = 'Zayar_test'

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('User subscription level card: generating, format', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()

  // we give ourselves some free diamond
  await ourClient
    .mutate({mutation: mutations.grantUserSubscriptionBonus})
    .then(({data: {grantUserSubscriptionBonus: user}}) => {
      expect(user.userId).toBe(ourUserId)
      expect(user.subscriptionLevel).toBe('DIAMOND')
    })
  await misc.sleep(2000)

  await ourClient.query({query: queries.self}).then(({data: {self: user}}) => {
    expect(user.userId).toBe(ourUserId)
    expect(user.cardCount).toBe(2)
    expect(user.cards.items).toHaveLength(2)
    let card = user.cards.items[0]
    expect(card.cardId).toBe(`${ourUserId}:USER_SUBSCRIPTION_LEVEL`)
    expect(card.title).toBe('Welcome to Diamond')
    expect(card.subTitle).toBe('Enjoy exclusive perks of being a subscriber')
    expect(card.action).toBe('https://real.app/diamond')
    // second card is the 'Add a profile photo'
    expect(user.cards.items[1].title).toBe('Add a profile photo')
  })
})

test('Grant user subscription level with FREE_FOR_LIFE grant code', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()

  // we give ourselves some free diamond
  await ourClient
    .mutate({mutation: mutations.grantUserSubscriptionBonus, variables: {grantCode: 'FREE_FOR_LIFE'}})
    .then(({data: {grantUserSubscriptionBonus: user}}) => {
      expect(user.userId).toBe(ourUserId)
      expect(user.subscriptionLevel).toBe('DIAMOND')
    })
  await misc.sleep(2000)

  await ourClient.query({query: queries.self}).then(({data: {self: user}}) => {
    expect(user.userId).toBe(ourUserId)
    expect(user.cardCount).toBe(2)
    expect(user.cards.items).toHaveLength(2)
    let card = user.cards.items[0]
    expect(card.cardId).toBe(`${ourUserId}:USER_SUBSCRIPTION_LEVEL`)
    expect(card.title).toBe('Welcome to Diamond')
    expect(card.subTitle).toBe('Enjoy exclusive perks of being a subscriber')
    expect(card.action).toBe('https://real.app/diamond')
    // second card is the 'Add a profile photo'
    expect(user.cards.items[1].title).toBe('Add a profile photo')
  })
})

test('Promote user level with invalid promotion code', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()

  const invalidPromotionCode = 'invalid'
  // we redeem promotion with promotion code
  await expect(
    ourClient.mutate({mutation: mutations.redeemPromotion, variables: {code: invalidPromotionCode}}),
  ).rejects.toThrow(/ClientError: User .* - Promotion code is not valid/)

  // verify the correct error codes are returned
  await ourClient
    .mutate({mutation: mutations.redeemPromotion, variables: {code: invalidPromotionCode}})
    .catch((err) => {
      expect(err.graphQLErrors[0].errorInfo).toEqual(['NOT_VALID'])
    })
})

test('Promote user subscription level with promotion code', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()
  const {client: otherClient, userId: otherUserId} = await loginCache.getCleanLogin()

  // we redeem promotion with 6 month promotion code
  await ourClient
    .mutate({mutation: mutations.redeemPromotion, variables: {code: promotionCode1}})
    .then(({data: {redeemPromotion: user}}) => {
      expect(user.userId).toBe(ourUserId)
      expect(user.subscriptionLevel).toBe('DIAMOND')
    })
  // they redeem promotion with free for life promotion code
  await theirClient
    .mutate({mutation: mutations.redeemPromotion, variables: {code: promotionCode2}})
    .then(({data: {redeemPromotion: user}}) => {
      expect(user.userId).toBe(theirUserId)
      expect(user.subscriptionLevel).toBe('DIAMOND')
    })
  await misc.sleep(2000)

  // other redeem promotion with free for life promotion code, not case sensitive
  await otherClient
    .mutate({mutation: mutations.redeemPromotion, variables: {code: promotionCode3}})
    .then(({data: {redeemPromotion: user}}) => {
      expect(user.userId).toBe(otherUserId)
      expect(user.subscriptionLevel).toBe('DIAMOND')
    })
  await misc.sleep(2000)

  await ourClient.query({query: queries.self}).then(({data: {self: user}}) => {
    expect(user.userId).toBe(ourUserId)
    expect(user.cardCount).toBe(2)
    expect(user.cards.items).toHaveLength(2)
    let card = user.cards.items[0]
    expect(card.cardId).toBe(`${ourUserId}:USER_SUBSCRIPTION_LEVEL`)
    expect(card.title).toBe('Welcome to Diamond')
    expect(card.subTitle).toBe('Enjoy exclusive perks of being a subscriber')
    expect(card.action).toBe('https://real.app/diamond')
    // second card is the 'Add a profile photo'
    expect(user.cards.items[1].title).toBe('Add a profile photo')
  })

  // we try to use redeem promotion code twice
  await expect(
    ourClient.mutate({mutation: mutations.redeemPromotion, variables: {code: promotionCode1}}),
  ).rejects.toThrow(/ClientError: User .* is already on DIAMOND/)
})
