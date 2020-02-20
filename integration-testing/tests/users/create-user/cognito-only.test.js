/* eslint-env jest */

const moment = require('moment')
const uuidv4 = require('uuid/v4')

const cognito = require('../../../utils/cognito.js')
const schema = require('../../../utils/schema.js')


describe('cognito-only user', () => {

  let client, accessToken

  beforeEach(async () => {
    client = undefined
    accessToken = undefined
  })

  afterEach(async () => {
    if (client) await client.mutate({mutation: schema.resetUser})
    if (accessToken) await cognito.userPoolClient.deleteUser({AccessToken: accessToken}).promise()
    // no way to delete ourselves from identity pool without developer credentials
  })

  test('Mutation.createCognitoOnlyUser fails if identity pool id and user pool "username" dont match', async () => {
    // create the user in the user pool, with a random username and email
    const cognitoUsername = 'us-east-1:' + uuidv4()  // looks like a cognito identity pool id to pass validation
    const password = cognito.generatePassword()
    const email = cognito.generateEmail()

    await cognito.userPoolClient.signUp({
      Username: cognitoUsername,
      Password: password,
      UserAttributes: [{
        Name: 'family_name',
        Value: cognito.familyName,
      }, {
        Name: 'email',
        Value: email,
      }],
    }).promise()

    // sign the user in
    let resp = await cognito.userPoolClient.initiateAuth({
      AuthFlow: 'USER_PASSWORD_AUTH',
      AuthParameters: {USERNAME: cognitoUsername, PASSWORD: password},
    }).promise()
    accessToken = resp['AuthenticationResult']['AccessToken']
    const idToken = resp['AuthenticationResult']['IdToken']

    // get an id for that user
    const logins = {[cognito.userPoolLoginsKey]: idToken}
    const idResp = await cognito.identityPoolClient.getId({Logins: logins}).promise()
    const userId = idResp['IdentityId']

    // get credentials for that user
    resp = await cognito.identityPoolClient.getCredentialsForIdentity({IdentityId: userId, Logins: logins}).promise()

    // get appsync client with those creds
    client = await cognito.getAppSyncClient(resp['Credentials'])

    // try to pick random username, register it - should fail
    let variables = {username: cognito.generateUsername()}
    await expect(client.mutate({mutation: schema.createCognitoOnlyUser, variables})).rejects.toThrow('ClientError')
  })

  test('Mutation.createCognitoOnlyUser succeds if identity pool id and user pool "username" match', async () => {
    // get un-authenticated userId
    const idResp = await cognito.identityPoolClient.getId().promise()
    const userId = idResp['IdentityId']
    const password = cognito.generatePassword()
    const email = cognito.generateEmail()

    // create the user in the user pool, with an email
    await cognito.userPoolClient.signUp({
      Username: userId,
      Password: password,
      UserAttributes: [{
        Name: 'family_name',
        Value: cognito.familyName,
      }, {
        Name: 'email',
        Value: email,
      }],
    }).promise()

    // sign the user in
    let resp = await cognito.userPoolClient.initiateAuth({
      AuthFlow: 'USER_PASSWORD_AUTH',
      AuthParameters: {USERNAME: userId, PASSWORD: password},
    }).promise()
    accessToken = resp['AuthenticationResult']['AccessToken']
    const idToken = resp['AuthenticationResult']['IdToken']

    // get credentials and link the two entries
    const logins = {[cognito.userPoolLoginsKey]: idToken}
    resp = await cognito.identityPoolClient.getCredentialsForIdentity({IdentityId: userId, Logins: logins}).promise()

    // get appsync client with those creds
    client = await cognito.getAppSyncClient(resp['Credentials'])

    // pick a random username, register it, check all is good!
    const username = cognito.generateUsername()
    const before = moment().toISOString()
    resp = await client.mutate({mutation: schema.createCognitoOnlyUser, variables: {username}})
    const after = moment().toISOString()
    expect(resp['errors']).toBeUndefined()
    expect(resp['data']['createCognitoOnlyUser']['userId']).toBe(userId)
    expect(resp['data']['createCognitoOnlyUser']['username']).toBe(username)
    expect(resp['data']['createCognitoOnlyUser']['email']).toBe(email)

    // check the signedUpAt is within our bookends
    const signedUpAt = resp['data']['createCognitoOnlyUser']['signedUpAt']
    expect(before <= signedUpAt).toBe(true)
    expect(after >= signedUpAt).toBe(true)
  })
})
