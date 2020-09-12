const cognito = require('../../utils/cognito')
const {mutations} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

let client, userId
beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => {
  const {IdentityId} = await cognito.identityPoolClient.getId().promise()
  const {Credentials} = await cognito.identityPoolClient.getCredentialsForIdentity({IdentityId}).promise()
  client = await cognito.getAppSyncClient(Credentials)
  userId = IdentityId
})
afterAll(async () => await loginCache.reset())

test('New full user without profile photo card: generating, format', async () => {
  // verify that new anonymous user do not get this card
  await client.mutate({mutation: mutations.createAnonymousUser}).then(({data: {createAnonymousUser: user}}) => {
    expect(user.userId).toBe(userId)
    expect(user.email).toBeNull()
    expect(user.userStatus).toBe('ANONYMOUS')
    expect(user.cards).toBeFalsy()
  })
})
