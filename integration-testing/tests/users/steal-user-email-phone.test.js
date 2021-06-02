import {cognito, eventually} from '../../utils'
import {mutations, queries} from '../../schema'

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin('+15105551333'))
  loginCache.addCleanLogin(await cognito.getAppSyncLogin('+15105551444'))
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Steal user email and phoneNumber exception', async () => {
  const {email: ourEmail, client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()

  const ourPhoneNumber = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.phoneNumber).toBeTruthy()
    return data.self.phoneNumber
  })

  await expect(
    theirClient.mutate({mutation: mutations.startChangeUserEmail, variables: {email: ourEmail}}),
  ).rejects.toThrow(/ClientError: User email is already used by other/)

  await expect(
    theirClient.mutate({
      mutation: mutations.startChangeUserPhoneNumber,
      variables: {phoneNumber: ourPhoneNumber},
    }),
  ).rejects.toThrow(/GraphQL error: ClientError: User phoneNumber is already used by other/)

  // Check error codes
  await theirClient
    .mutate({mutation: mutations.startChangeUserEmail, variables: {email: ourEmail}})
    .catch((err) => {
      expect(err.graphQLErrors[0].errorInfo).toEqual(['USER_ALREADY_EXISTS'])
    })

  await theirClient
    .mutate({mutation: mutations.startChangeUserPhoneNumber, variables: {phoneNumber: ourPhoneNumber}})
    .catch((err) => {
      expect(err.graphQLErrors[0].errorInfo).toEqual(['USER_ALREADY_EXISTS'])
    })
})
