/* Utils functions for use in tests
 *
 * Mostly for help in setup and teardown.
 */

const AWS = require('aws-sdk')
const AWSAppSyncClient = require('aws-appsync').default
const callerId = require('caller-id')
const dotenv = require('dotenv')
const jwtDecode = require('jwt-decode')
const md5 = require('md5')
const path = require('path')
const pwdGenerator = require('generate-password')
const uuidv4 = require('uuid/v4')
require('isomorphic-fetch')

const {mutations} = require('../schema')

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

const identityPoolClient = new AWS.CognitoIdentity({params: {IdentityPoolId: identityPoolId}})
const userPoolClient = new AWS.CognitoIdentityServiceProvider({params: {ClientId: cognitoClientId}})

// All users the test client creates must have this family name (or the sign up
// will be rejected). This is to make it easier to clean them out later.
const familyName = 'TESTER'

const AuthFlow = 'USER_PASSWORD_AUTH'

// To be used in the `Logins` parameter when calling the identity pool
const userPoolLoginsKey = `cognito-idp.${AWS.config.region}.amazonaws.com/${userPoolId}`
const googleLoginsKey = 'accounts.google.com'
const facebookLoginsKey = 'graph.facebook.com'

const generatePassword = () => {
  return pwdGenerator.generate({length: 8})
}

const generateUsername = () => familyName + uuidv4().substring(24)

const generateEmail = (substr) => {
  substr = substr || uuidv4().substring(24)
  return 'success+' + substr + '@simulator.amazonses.com'
}

/**
 * Given a set of callerData as returned by the callerId package,
 * generate and return a random-repeatable uuid v4
 */
const generateRRUuid = (callerData) => {
  // parse the caller data
  const repoRoot = path.dirname(path.dirname(__dirname))
  const callerFilePath = path.relative(repoRoot, callerData.filePath)
  const callerOrigin = callerFilePath + '#L' + callerData.lineNumber
  const callerHash = md5(callerOrigin) // 32-char hex string

  // covert to an 16-element byte array https://stackoverflow.com/a/34356351
  const callerBytes = []
  for (let c = 0; c < callerHash.length; c += 2) {
    callerBytes.push(parseInt(callerHash.substr(c, 2), 16))
  }

  return uuidv4({random: callerBytes})
}

const getAppSyncClient = async (creds) => {
  const credentials = new AWS.Credentials(creds.AccessKeyId, creds.SecretKey, creds.SessionToken)
  const client = new AWSAppSyncClient(
    {
      url: appsyncApiUrl,
      region: AWS.config.region,
      auth: {type: 'AWS_IAM', credentials},
      disableOffline: true,
    },
    // https://www.apollographql.com/docs/react/api/react-apollo/#optionsfetchpolicy
    {defaultOptions: {query: {fetchPolicy: 'network-only'}}},
  )
  await client.hydrated()
  return client
}

/**
 * Generate and return a client to use with the appsync endpoint, and some optional login details.
 * Re-uses the same login based on the file and line number from which this function is called.
 * @param newUserPhone If a new user is created, use this phone number.
 */
const getAppSyncLogin = async (newUserPhone) => {
  const myUuid = generateRRUuid(callerId.getData())
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
    const userId = await identityPoolClient
      .getId()
      .promise()
      .then(({IdentityId}) => IdentityId)

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
  const appSyncClient = await identityPoolClient
    .getCredentialsForIdentity({IdentityId: userId, Logins: {[userPoolLoginsKey]: idToken}})
    .promise()
    .then(({Credentials}) => getAppSyncClient(Credentials))

  const username = familyName + myUuid.substring(24)
  await appSyncClient.mutate(
    reusingExistingUser
      ? {mutation: mutations.resetUser, variables: {newUsername: username}}
      : {mutation: mutations.createCognitoOnlyUser, variables: {username}},
  )

  return [appSyncClient, userId, password, email, username]
}

/**
 * A class to help each test file re-use the same logins, thus
 * speeding up the tests and reducing orphaned objects.
 */
class AppSyncLoginCache {
  constructor() {
    this.cleanLogins = []
    this.dirtyLogins = []
  }

  addCleanLogin(login) {
    this.cleanLogins.push(login)
  }

  /* Return a clean login. If no clean logins are left, throws an exception. */
  async getCleanLogin() {
    const login = this.cleanLogins.pop()
    if (!login) throw new Error('No more clean logins left. Perhaps initialize more in beforeAll()?')
    this.dirtyLogins.push(login)
    return login
  }

  async clean() {
    // purposefully avoiding parallelism here so we can run more test suites in parrellel
    let login = this.dirtyLogins.pop()
    while (login) {
      const [client, , , , username] = login
      await client.clearStore()
      await client.mutate({mutation: mutations.resetUser, variables: {newUsername: username}})
      this.cleanLogins.push(login)
      login = this.dirtyLogins.pop()
    }
  }

  async reset() {
    // purposefully avoiding parallelism here so we can run more test suites in parrellel
    this.cleanLogins.forEach(([client]) => client.mutate({mutation: mutations.resetUser}))
    let login = this.dirtyLogins.pop()
    while (login) {
      const [client] = login
      await client.mutate({mutation: mutations.resetUser})
      this.cleanLogins.push(login)
      login = this.dirtyLogins.pop()
    }
  }
}

module.exports = {
  // most common
  AppSyncLoginCache,
  getAppSyncLogin,

  // clients
  userPoolClient,
  identityPoolClient,
  getAppSyncClient,

  // helpers
  generatePassword,
  generateUsername,
  generateEmail,
  generateRRUuid,

  // constants
  familyName,
  userPoolLoginsKey,
  googleLoginsKey,
  facebookLoginsKey,
  AuthFlow,
}
