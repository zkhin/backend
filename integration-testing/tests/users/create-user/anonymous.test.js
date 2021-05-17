const moment = require('moment')

const {cognito, eventually} = require('../../../utils')
const {mutations, queries} = require('../../../schema')

let client, userId
beforeEach(async () => {
  const {IdentityId} = await cognito.identityPoolClient.getId().promise()
  const {Credentials} = await cognito.identityPoolClient.getCredentialsForIdentity({IdentityId}).promise()
  client = await cognito.getAppSyncClient(Credentials)
  userId = IdentityId
})
afterEach(async () => {
  if (client) await client.mutate({mutation: mutations.deleteUser})
})

test('Mutation.createAnonymousUser success', async () => {
  // pick a random username, register it, check all is good!
  const before = moment().toISOString()
  const after = await client
    .mutate({mutation: mutations.createAnonymousUser})
    .then(({data: {createAnonymousUser: cognitoTokens}}) => {
      const after = moment().toISOString()
      expect(cognitoTokens.AccessToken).toBeTruthy()
      expect(cognitoTokens.ExpiresIn).toBeGreaterThan(0)
      expect(cognitoTokens.TokenType).toBe('Bearer')
      expect(cognitoTokens.RefreshToken).toBeTruthy()
      expect(cognitoTokens.IdToken).toBeTruthy()
      return after
    })

  // check that user really stuck in DB
  await client.query({query: queries.self}).then(({data: {self: user}}) => {
    expect(user.userId).toBe(userId)
    expect(user.username).toBeTruthy()
    expect(user.username).toMatch(new RegExp(`^user_?`))
    expect(user.email).toBeNull()
    expect(user.phoneNumber).toBeNull()
    expect(user.fullName).toBeNull()
    expect(user.userStatus).toBe('ANONYMOUS')
    expect(before <= user.signedUpAt).toBe(true)
    expect(after >= user.signedUpAt).toBe(true)
  })
  await client.query({query: queries.user, variables: {userId}}).then(({data: {user}}) => {
    expect(user.userId).toBe(userId)
    expect(user.username).toBeTruthy()
    expect(user.username).toMatch(new RegExp(`^user_?`))
    expect(user.userStatus).toBe('ANONYMOUS')
  })

  // check anonymous user can disable themselves
  await client
    .mutate({mutation: mutations.disableUser})
    .then(({data: {disableUser: user}}) => expect(user.userStatus).toBe('DISABLED'))
  await client
    .query({query: queries.self})
    .then(({data: {self: user}}) => expect(user.userStatus).toBe('DISABLED'))
})

test('Calling Mutation.createAnonymousUser with user that already exists is a ClientError', async () => {
  // create a user
  await client.mutate({mutation: mutations.createAnonymousUser})
  await client.query({query: queries.self}).then(({data: {self}}) => expect(self.userId).toBe(userId))

  // try to create the user again, should fail with ClientError
  await expect(client.mutate({mutation: mutations.createAnonymousUser})).rejects.toThrow(
    /ClientError: .* already exists/,
  )

  // anonymous user deletes themselves
  await client
    .mutate({mutation: mutations.deleteUser})
    .then(({data: {deleteUser: user}}) => expect(user.userStatus).toBe('DELETING'))
  await eventually(async () => {
    const {data} = await client.query({query: queries.user, variables: {userId}})
    expect(data.user).toBeNull()
  })
  client = null // signals to the afterEach() that no clean is needed

  // verify gone from identity pool as well
  // if the entry still exists in the identity pool, will throw a 'NotAuthorizedException'
  await eventually(async () => {
    let errCode
    try {
      await cognito.identityPoolClient.getCredentialsForIdentity({IdentityId: userId}).promise()
    } catch (err) {
      errCode = err.code
    }
    expect(errCode).toBe('ResourceNotFoundException')
  })
})
