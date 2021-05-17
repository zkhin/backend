const {cognito, eventually, sleep} = require('../../utils')
const {mutations, queries} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

let anonClient, anonUserId
beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => {
  if (anonClient) await anonClient.mutate({mutation: mutations.deleteUser})
  anonClient = null
})

const cardTitle = 'Reserve your username & sign up!'

describe('New normal users do not get the user upsell card', () => {
  let ourClient, ourUserId

  beforeAll(async () => {
    ;({client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin())
  })

  test('User is normal', async () => {
    await eventually(async () => {
      const {data} = await ourClient.query({query: queries.self})
      expect(data.self.userId).toBe(ourUserId)
      expect(data.self.email).toBeDefined()
      expect(data.self.userStatus).toBe('ACTIVE')
    })
  })

  test('User does not get the card', async () => {
    await sleep()
    await ourClient.query({query: queries.self}).then(({data}) => {
      expect(data.self.userId).toBe(ourUserId)
      expect(data.self.cards.items.filter((card) => card.title === cardTitle)).toHaveLength(0)
    })
  })
})

describe('New anonymous users and the user upsell card', () => {
  let cardId

  beforeAll(async () => {
    ;({client: anonClient, userId: anonUserId} = await cognito.getAnonymousAppSyncLogin())
  })

  test('User is anonymous', async () => {
    await eventually(async () => {
      const {data} = await anonClient.query({query: queries.self})
      expect(data.self.userId).toBe(anonUserId)
      expect(data.self.email).toBeNull()
      expect(data.self.userStatus).toBe('ANONYMOUS')
    })
  })

  test('User does automatically get the card and it has correct format', async () => {
    cardId = await eventually(async () => {
      const {data} = await anonClient.query({query: queries.self})
      expect(data.self.cards.items).toHaveLength(1)
      expect(data.self.cards.items[0].title).toBe(cardTitle)
      expect(data.self.cards.items[0].action).toBe(`https://real.app/signup/${anonUserId}`)
      expect(data.self.cards.items[0].cardId).toBe(`${anonUserId}:ANONYMOUS_USER_UPSELL`)
      return data.self.cards.items[0].cardId
    })
  })

  test('User can delete the card', async () => {
    // verify anonymous can dismiss the card
    await anonClient
      .mutate({mutation: mutations.deleteCard, variables: {cardId}})
      .then(({data}) => expect(data.deleteCard.cardId).toBe(cardId))
    await eventually(async () => {
      const {data} = await anonClient.query({query: queries.self})
      expect(data.self.cards.items.length).toBe(0)
    })
  })
})
