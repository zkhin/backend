/* eslint-env jest */

const cognito = require('../../../utils/cognito.js')
const misc = require('../../../utils/misc.js')
const schema = require('../../../utils/schema.js')

const AuthFlow = cognito.AuthFlow

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Mutation.createCognitoOnlyUser with invalid username fails', async () => {
  const [client, userId] = await loginCache.getCleanLogin()

  // reset the user to clear their presence from dynamo
  let resp = await client.mutate({mutation: schema.resetUser})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['resetUser']['userId']).toBe(userId)

  const unameTooShort = 'aa'
  const unameTooLong = 'a'.repeat(31)
  const unameBadChar = 'a!a'

  // verify we can't create a user for ourselves with an invalid username
  const mutation = schema.createCognitoOnlyUser
  await expect(client.mutate({mutation, variables: {username: unameTooShort}})).rejects.toBeDefined()
  await expect(client.mutate({mutation, variables: {username: unameTooLong}})).rejects.toBeDefined()
  await expect(client.mutate({ mutation, variables: {username: unameBadChar}})).rejects.toBeDefined()
})


test('User can login with username used in Mutation.createCognitoOnlyUser', async () => {
  const [client, userId, password] = await loginCache.getCleanLogin()

  // reset the user to clear their presence from dynamo
  let resp = await client.mutate({mutation: schema.resetUser})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['resetUser']['userId']).toBe(userId)

  // create a new user with a unique username
  const username = 'TESTERYESnoMAYBEso' + misc.shortRandomString()
  resp = await client.mutate({mutation: schema.createCognitoOnlyUser, variables: {username}})
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
  const [theirClient, theirUserId, theirPassword] = await loginCache.getCleanLogin()
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // get their username
  let resp = await theirClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['userId']).toBe(theirUserId)
  const theirUsername = resp['data']['self']['username']

  // reset our user to clear their presence from dynamo
  resp = await ourClient.mutate({mutation: schema.resetUser})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['resetUser']['userId']).toBe(ourUserId)

  // try to createCognitoOnlyUser for us with their username, should fail
  await expect(ourClient.mutate({
    mutation: schema.createCognitoOnlyUser,
    variables: {username: theirUsername}
  })).rejects.toBeDefined()

  // verify they can still login with their ousername
  const AuthParameters = {USERNAME: theirUsername.toLowerCase(), PASSWORD: theirPassword}
  resp = await cognito.userPoolClient.initiateAuth({AuthFlow, AuthParameters}).promise()
  expect(resp).toHaveProperty('AuthenticationResult.AccessToken')
  expect(resp).toHaveProperty('AuthenticationResult.ExpiresIn')
  expect(resp).toHaveProperty('AuthenticationResult.RefreshToken')
  expect(resp).toHaveProperty('AuthenticationResult.IdToken')
})


test('Mutation.createCognitoOnlyUser saves fullName and can pull email from cognito, phone is null', async () => {
  const [client, userId, , email] = await loginCache.getCleanLogin()

  // reset the user to clear their presence from dynamo
  let resp = await client.mutate({mutation: schema.resetUser})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['resetUser']['userId']).toBe(userId)

  // create a new user some deets
  const username = 'TESTERYESnoMAYBEso' + misc.shortRandomString()
  const fullName = 'my-full-name'
  resp = await client.mutate({mutation: schema.createCognitoOnlyUser, variables: {username, fullName}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createCognitoOnlyUser']['userId']).toBe(userId)
  expect(resp['data']['createCognitoOnlyUser']['username']).toBe(username)
  expect(resp['data']['createCognitoOnlyUser']['fullName']).toBe(fullName)
  expect(resp['data']['createCognitoOnlyUser']['email']).toBe(email)
  expect(resp['data']['createCognitoOnlyUser']['phoneNumber']).toBeNull()
})


test('Mutation.createCognitoOnlyUser can pull phone from cognito, if set', async () => {
  const phone = '+12125551212'
  const [client, userId] = await cognito.getAppSyncLogin(phone)

  // reset the user to clear their presence from dynamo
  let resp = await client.mutate({mutation: schema.resetUser})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['resetUser']['userId']).toBe(userId)

  // create a new user some deets
  const username = 'TESTERYESnoMAYBEso' + misc.shortRandomString()
  resp = await client.mutate({mutation: schema.createCognitoOnlyUser, variables: {username}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['createCognitoOnlyUser']['userId']).toBe(userId)
  expect(resp['data']['createCognitoOnlyUser']['username']).toBe(username)
  expect(resp['data']['createCognitoOnlyUser']['phoneNumber']).toBe(phone)
})
