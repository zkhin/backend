const cognito = require('../../utils/cognito')
const misc = require('../../utils/misc')
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

test('New anonymous users do not get the add profile photo card', async () => {
  ({client: anonClient, userId: anonUserId} = await cognito.getAnonymousAppSyncLogin())

  // verify that new anonymous user do not get this card
  await misc.sleep(2000)
  await anonClient.query({query: queries.self}).then(({data: {self: user}}) => {
    expect(user.userId).toBe(anonUserId)
    expect(user.email).toBeNull()
    expect(user.userStatus).toBe('ANONYMOUS')
    expect(user.cards.items.length).toBe(0);
  })
})
