import got from 'got'

import {cognito} from '../../../utils'
import {mutations} from '../../../schema'

const loginCache = new cognito.AppSyncLoginCache()

let anonClient, anonUserId

/* Run me as a one-off, as you'll have to get a valid google id token
 * for our app. Can be generated from https://developers.google.com/oauthplayground/
 *
 * The email the oauth token is generated for must be one which this amazon account
 * is authorized to send to.
 */
describe.skip('Mutation.linkGoogleLogin', () => {
  const googleIdToken = process.env.GOOGLE_ID_TOKEN

  beforeAll(async () => {
    loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  })
  beforeEach(async () => await loginCache.clean())
  afterAll(async () => await loginCache.reset())

  afterEach(async () => {
    if (anonClient) await anonClient.mutate({mutation: mutations.deleteUser})
    anonClient = null
  })

  test('Anonymous user', async () => {
    if (googleIdToken === undefined) throw new Error('Env var GOOGLE_ID_TOKEN must be defined')

    // get the email associated with the token from google
    const email = await got
      .get('https://oauth2.googleapis.com/tokeninfo', {searchParams: {id_token: googleIdToken}})
      .json()
      .then(({email, email_verified}) => {
        expect(email_verified).toBe('true') // it's a string... ?
        return email
      })

    ;({client: anonClient, userId: anonUserId} = await cognito.getAnonymousAppSyncLogin())

    await anonClient
      .mutate({mutation: mutations.linkGoogleLogin, variables: {googleIdToken}})
      .then(({data: {linkGoogleLogin: user}}) => {
        expect(user.userId).toBe(anonUserId)
        expect(user.email).toBe(email)
        expect(user.userStatus).toBe('ACTIVE')
      })
  })

  test('Active user', async () => {
    if (googleIdToken === undefined) throw new Error('Env var GOOGLE_ID_TOKEN must be defined')

    const {client: ourClient, userId: ourUserId, email: ourEmail} = await loginCache.getCleanLogin()

    await ourClient
      .mutate({mutation: mutations.linkGoogleLogin, variables: {googleIdToken}})
      .then(({data: {linkGoogleLogin: user}}) => {
        expect(user.userId).toBe(ourUserId)
        expect(user.email).toBe(ourEmail)
        expect(user.userStatus).toBe('ACTIVE')
      })

    // link google again
    await ourClient
      .mutate({mutation: mutations.linkGoogleLogin, variables: {googleIdToken}})
      .then(({data: {linkGoogleLogin: user}}) => {
        expect(user.userId).toBe(ourUserId)
        expect(user.email).toBe(ourEmail)
        expect(user.userStatus).toBe('ACTIVE')
      })
  })
})
