/* eslint-env jest */

const rp = require('request-promise-native')

const cognito = require('../../../utils/cognito.js')
const schema = require('../../../utils/schema.js')


/* Run me as a one-off, as you'll have to get a valid google id token
 * for our app. Can be generated from https://developers.facebook.com/tools/explorer/
 *
 * The email the oauth token is generated for must be one which this amazon account
 * is authorized to send to.
 */
describe.skip('facebook user', () => {

  const facebookAccessToken = process.env.FACEBOOK_ACCESS_TOKEN
  if (facebookAccessToken === undefined) throw new Error('Env var FACEBOOK_ACCESS_TOKEN must be defined')

  let client

  beforeEach(async () => {
    client = undefined
  })

  afterEach(async () => {
    if (client) await client.mutate({mutation: schema.resetUser})
    // no way to delete ourselves from identity pool without an access token
    // no way to delete ourselves from identity pool without developer credentials
  })

  test('Mutation.createFacebookUser success', async () => {
    // get the email associated with the token from google
    const profile = await rp.get({
      uri: 'https://graph.facebook.com/me',
      qs: {
        fields: 'email',
        access_token: facebookAccessToken,
      },
      json: true,
    })
    // facebook only returns verified emails
    // https://stackoverflow.com/questions/14280535/is-it-possible-to-check-if-an-email-is-confirmed-on-facebook
    const email = profile['email']

    // get and id and credentials from the identity pool
    const logins = {[cognito.facebookLoginsKey]: facebookAccessToken}
    let resp = await cognito.identityPoolClient.getId({Logins: logins}).promise()
    const userId = resp['IdentityId']
    resp = await cognito.identityPoolClient.getCredentialsForIdentity({IdentityId: userId, Logins: logins}).promise()

    // get appsync client with those creds
    client = await cognito.getAppSyncClient(resp['Credentials'])

    // pick a random username, register it, check all is good!
    const username = cognito.generateUsername()
    resp = await client.mutate({mutation: schema.createFacebookUser, variables: {username, facebookAccessToken}})
    expect(resp['errors']).toBeUndefined()
    expect(resp['data']['createFacebookUser']['userId']).toBe(userId)
    expect(resp['data']['createFacebookUser']['username']).toBe(username)
    expect(resp['data']['createFacebookUser']['email']).toBe(email)
    expect(resp['data']['createFacebookUser']['fullName']).toBeNull()
  })

  test('Mutation.createFacebookUser handles fullName correctly', async () => {
    // get the email associated with the token from google
    const profile = await rp.get({
      uri: 'https://graph.facebook.com/me',
      qs: {
        fields: 'email',
        access_token: facebookAccessToken,
      },
      json: true,
    })
    // facebook only returns verified emails
    // https://stackoverflow.com/questions/14280535/is-it-possible-to-check-if-an-email-is-confirmed-on-facebook
    const email = profile['email']

    // get and id and credentials from the identity pool
    const logins = {[cognito.facebookLoginsKey]: facebookAccessToken}
    let resp = await cognito.identityPoolClient.getId({Logins: logins}).promise()
    const userId = resp['IdentityId']
    resp = await cognito.identityPoolClient.getCredentialsForIdentity({IdentityId: userId, Logins: logins}).promise()

    // get appsync client with those creds
    client = await cognito.getAppSyncClient(resp['Credentials'])

    // verify we can't set a fullName of the empty string
    const username = cognito.generateUsername()
    let variables = {username, facebookAccessToken, fullName: ''}
    await expect(client.mutate({mutation: schema.createFacebookUser, variables})).rejects.toThrow('ClientError')

    // verify fullName saved correctly if we specify it
    const fullName = 'a full name'
    variables = {username, facebookAccessToken, fullName}
    resp = await client.mutate({mutation: schema.createFacebookUser, variables: {username, facebookAccessToken}})
    expect(resp['errors']).toBeUndefined()
    expect(resp['data']['createFacebookUser']['userId']).toBe(userId)
    expect(resp['data']['createFacebookUser']['username']).toBe(username)
    expect(resp['data']['createFacebookUser']['email']).toBe(email)
    expect(resp['data']['createFacebookUser']['fullName']).toBe(fullName)
  })
})
