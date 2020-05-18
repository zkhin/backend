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

const { mutations } = require('../schema')

dotenv.config()

const cognitoClientId = process.env.COGNITO_TESTING_CLIENT_ID
if (cognitoClientId === undefined) throw new Error('Env var COGNITO_TESTING_CLIENT_ID must be defined')

const awsRegion = process.env.AWS_REGION
if (awsRegion === undefined) throw new Error('Env var AWS_REGION must be defined')

const appsyncApiUrl = process.env.APPSYNC_GRAPHQL_URL
if (appsyncApiUrl === undefined) throw new Error('Env var APPSYNC_GRAPHQL_URL must be defined')

const identityPoolId = process.env.COGNITO_IDENTITY_POOL_ID
if (identityPoolId === undefined) throw new Error('Env var COGNITO_IDENTITY_POOL_ID must be defined')

const userPoolId = process.env.COGNITO_USER_POOL_ID
if (userPoolId === undefined) throw new Error('Env var COGNITO_USER_POOL_ID must be defined')


const userPoolClient = new AWS.CognitoIdentityServiceProvider({params: {
  ClientId: cognitoClientId,
  Region: awsRegion,
}})

const identityPoolClient = new AWS.CognitoIdentity({params: {
  IdentityPoolId: identityPoolId,
}})

// All users the test client creates must have this family name (or the sign up
// will be rejected). This is to make it easier to clean them out later.
const familyName = 'TESTER'

const AuthFlow = 'USER_PASSWORD_AUTH'

// To be used in the `Logins` parameter when calling the identity pool
const userPoolLoginsKey = `cognito-idp.${awsRegion}.amazonaws.com/${userPoolId}`
const googleLoginsKey = 'accounts.google.com'
const facebookLoginsKey = 'graph.facebook.com'

const generatePassword = () => {
  return pwdGenerator.generate({length: 8})
}

const generateUsername = () => familyName + uuidv4().substring(24)

const generateEmail = (substr) => {
  substr = substr  || uuidv4().substring(24)
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
  const callerHash = md5(callerOrigin)  // 32-char hex string

  // covert to an 16-element byte array https://stackoverflow.com/a/34356351
  const callerBytes = []
  for (let c = 0; c < callerHash.length; c += 2) {
    callerBytes.push(parseInt(callerHash.substr(c, 2), 16))
  }

  return uuidv4({random: callerBytes})
}

const getAppSyncClient = async (creds) => {
  const credsObj = new AWS.Credentials(creds.AccessKeyId, creds.SecretKey, creds.SessionToken)
  const client = new AWSAppSyncClient({
    url: appsyncApiUrl,
    region: awsRegion,
    auth: {
      type: 'AWS_IAM',
      credentials: credsObj,
    },
    disableOffline: true,
  }, {
    defaultOptions: {
      query: {
        // https://www.apollographql.com/docs/react/api/react-apollo/#optionsfetchpolicy
        fetchPolicy: 'network-only',
        errorPolicy: 'all',
      },
    },
  })
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
  const password = myUuid + '-1.Aa'  // fulfill password requirements

  // try to sign the user in, and if that doesn't work, create the user
  let idToken, userId, userNeedsReset
  const AuthParameters = {USERNAME: email, PASSWORD: password}

  try {
    // succeds if the user already exists
    const authResp = await userPoolClient.initiateAuth({AuthFlow, AuthParameters}).promise()
    idToken = authResp.AuthenticationResult.IdToken
    userNeedsReset = true
    userId = jwtDecode(idToken)['cognito:username']
  } catch (err) {
    if (err.code !== 'NotAuthorizedException') throw(err)
    // user does not exist, we must create them. No need to reset it later on, as new user starts fresh
    userNeedsReset = false

    // get an unathenticated ID from the identity pool
    const idResp = await identityPoolClient.getId().promise()
    userId = idResp.IdentityId

    // create user in the user pool, using the 'identity id' from the identity pool as the user pool 'username'
    const UserAttributes = [
      {Name: 'family_name', Value: familyName },
      {Name: 'email', Value: email},
    ]
    if (newUserPhone) UserAttributes.push({Name: 'phone_number', Value: newUserPhone})
    const ClientMetadata = {autoConfirmUser: 'true'}
    await userPoolClient.signUp({Username: userId, Password: password, UserAttributes, ClientMetadata}).promise()

    // sign the user in
    const authResp = await userPoolClient.initiateAuth({AuthFlow, AuthParameters}).promise()
    idToken = authResp.AuthenticationResult.IdToken
  }
  const Logins = {[userPoolLoginsKey]: idToken}

  // get some credentials to use with the graphql client
  // note that for a new user, this step also adds an entry in the 'Logins' array of the entry in
  // in the identity pool for the entry in the user pool.
  const credsResp = await identityPoolClient.getCredentialsForIdentity({IdentityId: userId, Logins}).promise()
  const appSyncClient = await getAppSyncClient(credsResp.Credentials)

  const username = familyName + myUuid.substring(24)
  if (userNeedsReset) {
    // one call resets the user and then does the equivalent of calling Mutation.createCognitoOnlyUser()
    await appSyncClient.mutate({mutation: mutations.resetUser, variables: {newUsername: username}})
  }
  else {
    await appSyncClient.mutate({mutation: mutations.createCognitoOnlyUser, variables: {username}})
  }

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
    let login = this.dirtyLogins.pop()
    while (login) {
      const client = login[0]
      const username = login[4]
      await client.clearStore()
      await client.mutate({mutation: mutations.resetUser, variables: {newUsername: username}})
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
