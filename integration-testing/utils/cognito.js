/* Utils functions for use in tests
 *
 * Mostly for help in setup and teardown.
 */

// required by aws-appsync#aws-appsync-subscription-link
import ws from 'ws'
global.WebSocket = ws

import AWS from 'aws-sdk'
import {AWSAppSyncClient, createAppSyncLink} from 'aws-appsync'
import {setContext} from 'apollo-link-context'
import {ApolloLink} from 'apollo-link'
import {createHttpLink} from 'apollo-link-http'
import callsites from 'callsites'
import dotenv from 'dotenv'
import fetch from 'cross-fetch'
import jwtDecode from 'jwt-decode'
import md5 from 'md5'
import path from 'path'
import pwdGenerator from 'generate-password'
import {v4 as uuidv4} from 'uuid'

import {mutations, queries} from '../schema'
import {repoRoot} from './misc'
import {sleep} from './timing'

dotenv.config()
AWS.config = new AWS.Config()

const cognitoClientId = process.env.COGNITO_TESTING_CLIENT_ID
if (cognitoClientId === undefined) throw new Error('Env var COGNITO_TESTING_CLIENT_ID must be defined')

const appsyncApiUrl = process.env.APPSYNC_GRAPHQL_URL
if (appsyncApiUrl === undefined) throw new Error('Env var APPSYNC_GRAPHQL_URL must be defined')

const identityPoolId = process.env.COGNITO_IDENTITY_POOL_ID
if (identityPoolId === undefined) throw new Error('Env var COGNITO_IDENTITY_POOL_ID must be defined')

const userPoolId = process.env.COGNITO_USER_POOL_ID
if (userPoolId === undefined) throw new Error('Env var COGNITO_USER_POOL_ID must be defined')

export const identityPoolClient = new AWS.CognitoIdentity({params: {IdentityPoolId: identityPoolId}})
export const userPoolClient = new AWS.CognitoIdentityServiceProvider({params: {ClientId: cognitoClientId}})

// All users the test client creates must have this family name (or the sign up
// will be rejected). This is to make it easier to clean them out later.
export const familyName = 'TESTER'

export const AuthFlow = 'USER_PASSWORD_AUTH'

// To be used in the `Logins` parameter when calling the identity pool
export const userPoolLoginsKey = `cognito-idp.${AWS.config.region}.amazonaws.com/${userPoolId}`
export const googleLoginsKey = 'accounts.google.com'

export const generatePassword = () => {
  return pwdGenerator.generate({length: 8})
}

export const generateUsername = () => familyName + uuidv4().substring(24)

export const generateEmail = (substr) => {
  substr = substr || uuidv4().substring(24)
  return 'success+' + substr + '@simulator.amazonses.com'
}

/**
 * Given a callsite object as returned by the callsites package,
 * generate and return a random-repeatable uuid v4
 */
export const generateRRUuid = (callsite) => {
  // parse the caller data
  const callerFilePath = path.relative(repoRoot, callsite.getFileName())
  const callerOrigin = callerFilePath + '#L' + callsite.getLineNumber()
  const callerHash = md5(callerOrigin) // 32-char hex string

  // covert to an 16-element byte array https://stackoverflow.com/a/34356351
  const callerBytes = []
  for (let c = 0; c < callerHash.length; c += 2) {
    callerBytes.push(parseInt(callerHash.substr(c, 2), 16))
  }

  return uuidv4({random: callerBytes})
}

export const getAppSyncClient = async (creds) => {
  const credentials = new AWS.Credentials(creds.AccessKeyId, creds.SecretKey, creds.SessionToken)
  const appSyncClientOptions = {disableOffline: true}
  const apolloClientOptions = {
    defaultOptions: {query: {fetchPolicy: 'no-cache'}},
    link: createAppSyncLink({
      auth: {type: 'AWS_IAM', credentials},
      region: AWS.config.region,
      url: appsyncApiUrl,
      resultsFetcherLink: ApolloLink.from([
        setContext((request, previousContext) => ({
          headers: {
            ...previousContext.headers,
            ['x-real-version']: '0.1.0',
            ['x-real-device']: 'TestingClient',
            ['x-real-system']: 'REAL Backend Integration Tests',
            ['x-real-uid']: uuidv4().substring(24),
          },
        })),
        createHttpLink({uri: appsyncApiUrl, fetch}),
      ]),
    }),
  }
  return new AWSAppSyncClient(appSyncClientOptions, apolloClientOptions)
}

/**
 * Generate and return a client to use with the appsync endpoint, and some optional login details.
 * Re-uses the same login based on the file and line number from which this function is called.
 * @param newUserPhone If a new user is created, use this phone number.
 */
export const getAppSyncLogin = async (newUserPhone) => {
  const myUuid = generateRRUuid(callsites()[1])
  const email = generateEmail(myUuid.substring(24).toLowerCase())
  const password = myUuid + '-1.Aa' // fulfill password requirements

  // try to sign the user in, and if that doesn't work, create the user
  const AuthParameters = {USERNAME: email, PASSWORD: password}
  let idToken
  let reusingExistingUser = true
  try {
    // succeds if the user already exists
    idToken = await userPoolClient
      .initiateAuth({AuthFlow, AuthParameters})
      .promise()
      .then(({AuthenticationResult}) => AuthenticationResult.IdToken)
  } catch (err) {
    if (err.code !== 'NotAuthorizedException') throw err
    // user does not exist, we must create them. No need to reset it later on, as new user starts fresh
    reusingExistingUser = false

    // get an unathenticated ID from the identity pool, then
    // create user in the user pool, using the 'identity id' from the identity pool as the user pool 'username'
    const {IdentityId: userId} = await identityPoolClient.getId().promise()
    await userPoolClient
      .signUp({
        Username: userId,
        Password: password,
        UserAttributes: [
          {Name: 'family_name', Value: familyName},
          {Name: 'email', Value: email},
          ...(newUserPhone ? [{Name: 'phone_number', Value: newUserPhone}] : []),
        ],
        ClientMetadata: {autoConfirmUser: 'true'},
      })
      .promise()

    // sign the user in
    idToken = await userPoolClient
      .initiateAuth({AuthFlow, AuthParameters})
      .promise()
      .then(({AuthenticationResult}) => AuthenticationResult.IdToken)
  }
  const userId = jwtDecode(idToken)['cognito:username']

  // get some credentials to use with the graphql client
  // note that for a new user, this step also adds an entry in the 'Logins' array of the entry in
  // in the identity pool for the entry in the user pool.
  // Someimtes the identity pool randomly rejects credentials, but if you try again immediately,
  // it accepts them.
  let creds
  let retries = 2
  while (retries > 0) {
    try {
      ;({Credentials: creds} = await identityPoolClient
        .getCredentialsForIdentity({IdentityId: userId, Logins: {[userPoolLoginsKey]: idToken}})
        .promise())
      break
    } catch (err) {
      if (err.code !== 'NotAuthorizedException') throw err
      console.warn(`Cognito identity pool rejected user '${userId}'s idToken '${idToken}' with error: ${err}`)
    }
    retries -= 1
  }
  if (!creds) throw Error(`User '${userId}' failed to get credentials from cognito identity pool`)

  const appSyncClient = await getAppSyncClient(creds)
  const username = familyName + myUuid.substring(24)
  await appSyncClient.mutate(
    reusingExistingUser
      ? {mutation: mutations.resetUser, variables: {newUsername: username}}
      : {mutation: mutations.createCognitoOnlyUser, variables: {username}},
  )

  return {client: appSyncClient, userId, password, email, username}
}

/**
 * Generate an new anonymous user with a ready-to-go fully-initialized gql client.
 **/
export const getAnonymousAppSyncLogin = async () => {
  const {IdentityId} = await identityPoolClient.getId().promise()
  const {Credentials} = await identityPoolClient.getCredentialsForIdentity({IdentityId}).promise()
  const client = await getAppSyncClient(Credentials)
  await client.mutate({mutation: mutations.createAnonymousUser})
  const {userId, username} = await client.query({query: queries.self}).then(({data: {self}}) => self)
  return {client, userId, username}
}

/**
 * A class to help each test file re-use the same logins, thus
 * speeding up the tests and reducing orphaned objects.
 */
export class AppSyncLoginCache {
  constructor() {
    this.cleanLogins = []
    this.dirtyLogins = []
  }

  addCleanLogin(login) {
    this.cleanLogins.push({login, timer: Promise.resolve()})
  }

  /* Return a clean login. If no clean logins are left, throws an exception. */
  async getCleanLogin() {
    const {login, timer} = this.cleanLogins.pop()
    if (!login) throw new Error('No more clean logins left. Perhaps initialize more in beforeAll()?')
    this.dirtyLogins.push(login)
    await timer // give post-user-reset dyanmo stream handlers time to run
    return login
  }

  async clean() {
    // purposefully avoiding parallelism here so we can run more test suites in parrellel
    let login = this.dirtyLogins.pop()
    while (login) {
      const {client, username} = login
      await client.clearStore()
      await client.mutate({mutation: mutations.resetUser, variables: {newUsername: username}})
      this.cleanLogins.push({login, timer: sleep(3)})
      login = this.dirtyLogins.pop()
    }
  }

  async reset() {
    // purposefully avoiding parallelism here so we can run more test suites in parrellel
    while (this.cleanLogins.length > 0) {
      const {login, timer} = this.cleanLogins.pop()
      await timer
      await login.client.mutate({mutation: mutations.resetUser})
    }
    while (this.dirtyLogins.length > 0) {
      const {client} = this.dirtyLogins.pop()
      await client.mutate({mutation: mutations.resetUser})
    }
  }
}
