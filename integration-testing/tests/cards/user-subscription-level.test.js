import {cognito, deleteDefaultCard, eventually} from '../../utils'
import {mutations, queries} from '../../schema'

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
  await deleteDefaultCard(ourClient)

  // we give ourselves some free diamond
  await ourClient
    .mutate({mutation: mutations.grantUserSubscriptionBonus})
    .then(({data: {grantUserSubscriptionBonus: user}}) => {
      expect(user.userId).toBe(ourUserId)
      expect(user.subscriptionLevel).toBe('DIAMOND')
    })

  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    let card = data.self.cards.items[0]
    expect(card.cardId).toBe(`${ourUserId}:USER_SUBSCRIPTION_LEVEL`)
    expect(card.title).toBe('Welcome to Diamond')
    expect(card.subTitle).toBe('Enjoy exclusive perks of being a subscriber')
    expect(card.action).toBe('https://real.app/diamond')
  })
})

test('Grant user subscription level with FREE_FOR_LIFE grant code', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  await deleteDefaultCard(ourClient)

  // we give ourselves some free diamond
  await ourClient
    .mutate({mutation: mutations.grantUserSubscriptionBonus, variables: {grantCode: 'FREE_FOR_LIFE'}})
    .then(({data: {grantUserSubscriptionBonus: user}}) => {
      expect(user.userId).toBe(ourUserId)
      expect(user.subscriptionLevel).toBe('DIAMOND')
    })

  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    let card = data.self.cards.items[0]
    expect(card.cardId).toBe(`${ourUserId}:USER_SUBSCRIPTION_LEVEL`)
    expect(card.title).toBe('Welcome to Diamond')
    expect(card.subTitle).toBe('Enjoy exclusive perks of being a subscriber')
    expect(card.action).toBe('https://real.app/diamond')
  })
})

test('Promote user level with invalid promotion code', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()

  const invalidPromotionCode = 'invalid'
  // we redeem promotion with promotion code
  await ourClient
    .mutate({mutation: mutations.redeemPromotion, variables: {code: invalidPromotionCode}, errorPolicy: 'all'})
    .then(({errors}) => {
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toMatch(/ClientError: User .* - Promotion code is not valid/)
    })

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
  await deleteDefaultCard(ourClient)

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

  // other redeem promotion with free for life promotion code, not case sensitive
  await otherClient
    .mutate({mutation: mutations.redeemPromotion, variables: {code: promotionCode3}})
    .then(({data: {redeemPromotion: user}}) => {
      expect(user.userId).toBe(otherUserId)
      expect(user.subscriptionLevel).toBe('DIAMOND')
    })

  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBe(1)
    expect(data.self.cards.items).toHaveLength(1)
    let card = data.self.cards.items[0]
    expect(card.cardId).toBe(`${ourUserId}:USER_SUBSCRIPTION_LEVEL`)
    expect(card.title).toBe('Welcome to Diamond')
    expect(card.subTitle).toBe('Enjoy exclusive perks of being a subscriber')
    expect(card.action).toBe('https://real.app/diamond')
  })

  // we try to use redeem promotion code twice
  await ourClient
    .mutate({mutation: mutations.redeemPromotion, variables: {code: promotionCode1}, errorPolicy: 'all'})
    .then(({errors}) => {
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toMatch(
        /ClientError: User .* has already granted themselves a subscription bonus/,
      )
    })
})

test('Grant subscription -> Redeem promotion per user', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()

  // we give ourselves some free diamond
  await ourClient
    .mutate({mutation: mutations.grantUserSubscriptionBonus})
    .then(({data: {grantUserSubscriptionBonus: user}}) => {
      expect(user.userId).toBe(ourUserId)
      expect(user.subscriptionLevel).toBe('DIAMOND')
    })

  await ourClient
    .mutate({mutation: mutations.grantUserSubscriptionBonus, errorPolicy: 'all'})
    .then(({errors}) => {
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toMatch(
        /ClientError: User .* has already granted themselves a subscription bonus/,
      )
    })

  await ourClient
    .mutate({mutation: mutations.redeemPromotion, variables: {code: promotionCode3}})
    .then(({data: {redeemPromotion: user}}) => {
      expect(user.userId).toBe(ourUserId)
      expect(user.subscriptionLevel).toBe('DIAMOND')
    })

  await ourClient
    .mutate({mutation: mutations.redeemPromotion, variables: {code: promotionCode1}, errorPolicy: 'all'})
    .then(({errors}) => {
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toMatch(
        /ClientError: User .* has already granted themselves a subscription bonus/,
      )
    })
})

test('Redeem promotion -> Grant subscription per user', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()

  await ourClient
    .mutate({mutation: mutations.redeemPromotion, variables: {code: promotionCode3}})
    .then(({data: {redeemPromotion: user}}) => {
      expect(user.userId).toBe(ourUserId)
      expect(user.subscriptionLevel).toBe('DIAMOND')
    })

  // we give ourselves some free diamond
  await ourClient
    .mutate({mutation: mutations.grantUserSubscriptionBonus, errorPolicy: 'all'})
    .then(({errors}) => {
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toMatch(
        /ClientError: User .* has already granted themselves a subscription bonus/,
      )
    })
})
