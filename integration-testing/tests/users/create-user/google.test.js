const rp = require('request-promise-native')

const cognito = require('../../../utils/cognito.js')
const {mutations} = require('../../../schema')

jest.retryTimes(2)

/* Run me as a one-off, as you'll have to get a valid google id token
 * for our app. Can be generated from https://developers.google.com/oauthplayground/
 *
 * The email the oauth token is generated for must be one which this amazon account
 * is authorized to send to.
 */
describe.skip('google user', () => {
  const googleIdToken = process.env.GOOGLE_ID_TOKEN
  let client

  beforeEach(async () => {
    client = undefined
  })

  afterEach(async () => {
    if (client) await client.mutate({mutation: mutations.resetUser})
    // no way to delete ourselves from identity pool without an access token
    // no way to delete ourselves from identity pool without developer credentials
  })

  test('Mutation.createGoogleUser success', async () => {
    if (googleIdToken === undefined) throw new Error('Env var GOOGLE_ID_TOKEN must be defined')

    // get the email associated with the token from google
    const tokenInfo = await rp.get({
      uri: 'https://oauth2.googleapis.com/tokeninfo',
      qs: {id_token: googleIdToken},
      json: true,
    })
    expect(tokenInfo['email_verified']).toBe('true') // it's a string... ?
    const email = tokenInfo['email']

    // get and id and credentials from the identity pool
    const logins = {[cognito.googleLoginsKey]: googleIdToken}
    let resp = await cognito.identityPoolClient.getId({Logins: logins}).promise()
    const userId = resp['IdentityId']
    resp = await cognito.identityPoolClient
      .getCredentialsForIdentity({IdentityId: userId, Logins: logins})
      .promise()

    // get appsync client with those creds
    client = await cognito.getAppSyncClient(resp['Credentials'])

    // pick a random username, register it, check all is good!
    const username = cognito.generateUsername()
    const fullName = 'a full name'
    let variables = {username, googleIdToken, fullName}
    resp = await client.mutate({mutation: mutations.createGoogleUser, variables})
    expect(resp['errors']).toBeUndefined()
    expect(resp['data']['createGoogleUser']['userId']).toBe(userId)
    expect(resp['data']['createGoogleUser']['username']).toBe(username)
    expect(resp['data']['createGoogleUser']['email']).toBe(email)
    expect(resp['data']['createGoogleUser']['fullName']).toBe(fullName)
  })
})
