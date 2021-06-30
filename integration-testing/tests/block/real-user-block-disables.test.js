import {cognito, eventually, realUser} from '../../utils'
import {mutations, queries} from '../../schema'

const loginCache = new cognito.AppSyncLoginCache()
let realClient, realUserId

beforeAll(async () => {
  ;({client: realClient, userId: realUserId} = await realUser.getLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => {
  await loginCache.clean()
})
afterAll(async () => {
  await loginCache.reset()
})

test('When a user is blocked by the real user, they are force-disabled', async () => {
  // the real user has a random username at this point from the [before|after]_each methods
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()

  // we block the real user, verify real user is _not_ disabled
  await ourClient
    .mutate({mutation: mutations.blockUser, variables: {userId: realUserId}})
    .then(({data: {blockUser: user}}) => {
      expect(user.userId).toBe(realUserId)
      expect(user.blockedStatus).toBe('BLOCKING')
    })
  await eventually(async () => {
    const {data} = await realClient.query({query: queries.self})
    expect(data.self.userStatus).toBe('ACTIVE')
  })

  // real user blocks us, verify we are force-disabled and nothing happens to the real user
  await ourClient.query({query: queries.self}).then(({data: {self}}) => expect(self.userStatus).toBe('ACTIVE'))
  await realClient
    .mutate({mutation: mutations.blockUser, variables: {userId: ourUserId}})
    .then(({data: {blockUser: user}}) => {
      expect(user.userId).toBe(ourUserId)
      expect(user.blockedStatus).toBe('BLOCKING')
    })
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userStatus).toBe('DISABLED')
  })
  await realClient.query({query: queries.self}).then(({data: {self}}) => expect(self.userStatus).toBe('ACTIVE'))
})
