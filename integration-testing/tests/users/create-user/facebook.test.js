const rp = require('request-promise-native')

const cognito = require('../../../utils/cognito.js')
const {mutations} = require('../../../schema')

jest.retryTimes(1)

/* Run me as a one-off, as you'll have to get a valid facebook access token
 * for our app. Can be generated from https://developers.facebook.com/tools/explorer/
 *
 * The email the oauth token is generated for must be one which this amazon account
 * is authorized to send to.
 */
describe.skip('facebook user', () => {
  const facebookAccessToken = process.env.FACEBOOK_ACCESS_TOKEN
  let client

  beforeEach(async () => {
    client = undefined
  })

  afterEach(async () => {
    if (client) await client.mutate({mutation: mutations.resetUser})
  })

  test('Mutation.createFacebookUser success', async () => {
    if (facebookAccessToken === undefined) throw new Error('Env var FACEBOOK_ACCESS_TOKEN must be defined')

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
    resp = await cognito.identityPoolClient
      .getCredentialsForIdentity({IdentityId: userId, Logins: logins})
      .promise()

    // get appsync client with those creds
    client = await cognito.getAppSyncClient(resp['Credentials'])

    // pick a random username, register it, check all is good!
    const username = cognito.generateUsername()
    const fullName = 'a full name'
    let variables = {username, facebookAccessToken, fullName}
    resp = await client.mutate({mutation: mutations.createFacebookUser, variables})
    expect(resp['errors']).toBeUndefined()
    expect(resp['data']['createFacebookUser']['userId']).toBe(userId)
    expect(resp['data']['createFacebookUser']['username']).toBe(username)
    expect(resp['data']['createFacebookUser']['email']).toBe(email)
    expect(resp['data']['createFacebookUser']['fullName']).toBe(fullName)
  })
})
