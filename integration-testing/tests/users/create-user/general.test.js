import {cognito, shortRandomString} from '../../../utils'
import {mutations, queries} from '../../../schema'

const AuthFlow = cognito.AuthFlow
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Mutation.createCognitoOnlyUser with invalid username fails', async () => {
  const {client, userId} = await loginCache.getCleanLogin()

  // reset the user to clear their presence from dynamo
  let resp = await client.mutate({mutation: mutations.resetUser})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['resetUser']['userId']).toBe(userId)

  const unameTooShort = 'aa'
  const unameTooLong = 'a'.repeat(31)
  const unameBadChar = 'a!a'

  // verify we can't create a user for ourselves with an invalid username
  const mutation = mutations.createCognitoOnlyUser
  await expect(client.mutate({mutation, variables: {username: unameTooShort}})).rejects.toThrow(
    /ClientError: Username .* does not validate/,
  )
  await expect(client.mutate({mutation, variables: {username: unameTooLong}})).rejects.toThrow(
    /ClientError: Username .* does not validate/,
  )
  await expect(client.mutate({mutation, variables: {username: unameBadChar}})).rejects.toThrow(
    /ClientError: Username .* does not validate/,
  )
})

test('User can login with username used in Mutation.createCognitoOnlyUser', async () => {
  const {client, userId, password} = await loginCache.getCleanLogin()

  // reset the user to clear their presence from dynamo
  let resp = await client.mutate({mutation: mutations.resetUser})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['resetUser']['userId']).toBe(userId)

  // create a new user with a unique username
  const username = 'TESTERYESnoMAYBEso' + shortRandomString()
  resp = await client.mutate({mutation: mutations.createCognitoOnlyUser, variables: {username}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createCognitoOnlyUser']['userId']).toBe(userId)
  expect(resp['data']['createCognitoOnlyUser']['username']).toBe(username)

  // try to login as the user in cognito with that new username, lowered
  const AuthParameters = {USERNAME: username.toLowerCase(), PASSWORD: password}
  resp = await cognito.userPoolClient.initiateAuth({AuthFlow, AuthParameters}).promise()
  expect(resp).toHaveProperty('AuthenticationResult.AccessToken')
  expect(resp).toHaveProperty('AuthenticationResult.ExpiresIn')
  expect(resp).toHaveProperty('AuthenticationResult.RefreshToken')
  expect(resp).toHaveProperty('AuthenticationResult.IdToken')
})

test('Username collision causes Mutation.createCognitoOnlyUser to fail', async () => {
  const {client: theirClient, userId: theirUserId, password: theirPassword} = await loginCache.getCleanLogin()
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()

  // get their username
  let resp = await theirClient.query({query: queries.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['userId']).toBe(theirUserId)
  const theirUsername = resp['data']['self']['username']

  // reset our user to clear their presence from dynamo
  resp = await ourClient.mutate({mutation: mutations.resetUser})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['resetUser']['userId']).toBe(ourUserId)

  // try to createCognitoOnlyUser for us with their username, should fail
  await expect(
    ourClient.mutate({mutation: mutations.createCognitoOnlyUser, variables: {username: theirUsername}}),
  ).rejects.toThrow(/ClientError: Username .* already taken /)

  // verify they can still login with their ousername
  const AuthParameters = {USERNAME: theirUsername.toLowerCase(), PASSWORD: theirPassword}
  resp = await cognito.userPoolClient.initiateAuth({AuthFlow, AuthParameters}).promise()
  expect(resp).toHaveProperty('AuthenticationResult.AccessToken')
  expect(resp).toHaveProperty('AuthenticationResult.ExpiresIn')
  expect(resp).toHaveProperty('AuthenticationResult.RefreshToken')
  expect(resp).toHaveProperty('AuthenticationResult.IdToken')
})

describe('Mutation.createCognitoOnlyUser', () => {
  describe('when phone is null', () => {
    let client, userId, email

    beforeEach(async () => {
      ;({client, userId, email} = await loginCache.getCleanLogin())
      // reset the user to clear their presence from dynamo
      await client
        .mutate({mutation: mutations.resetUser})
        .then(({data: {resetUser}}) => expect(resetUser).toMatchObject({userId}))
    })

    afterEach(async () => {
      await client.mutate({mutation: mutations.resetUser})
    })

    it('saves fullName and email from cognito', async () => {
      // create a new user some deets
      const username = 'TESTERYESnoMAYBEso' + shortRandomString()
      const fullName = 'my-full-name'
      await client
        .mutate({mutation: mutations.createCognitoOnlyUser, variables: {username, fullName}})
        .then(({data: {createCognitoOnlyUser: user}}) => {
          expect(user).toMatchObject({userId, username, fullName, email, phoneNumber: null})
        })
    })
  })

  describe('when phone is not null', () => {
    const phone = '+12125551212'
    let client, userId

    beforeEach(async () => {
      ;({client, userId} = await cognito.getAppSyncLogin(phone))
      // reset the user to clear their presence from dynamo
      await client
        .mutate({mutation: mutations.resetUser})
        .then(({data: {resetUser}}) => expect(resetUser).toMatchObject({userId}))
    })

    afterEach(async () => {
      await client.mutate({mutation: mutations.resetUser})
    })

    it('saves phone from cognito', async () => {
      const username = 'TESTERYESnoMAYBEso' + shortRandomString()
      await client
        .mutate({mutation: mutations.createCognitoOnlyUser, variables: {username}})
        .then(({data: {createCognitoOnlyUser: user}}) => {
          expect(user).toMatchObject({userId, username, phoneNumber: phone})
        })
    })
  })
})
