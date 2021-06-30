import callsites from 'callsites'
import jwtDecode from 'jwt-decode'
import {
  AuthFlow,
  familyName,
  generateEmail,
  generateRRUuid,
  getAppSyncClient,
  identityPoolClient,
  userPoolClient,
  userPoolLoginsKey,
} from './cognito'
import {mutations} from '../schema'
import {sleep} from './timing'

let realLogin = null
const username = 'real'

class LostRaceConditionToCreateRealUser extends Error {}

/**
 * The real user is never reset or cleaned. This means that:
 *  - it persists between test runs
 *  - we can run tests that use the real user in parallel
 *  - any state it adds will not be automatically deleted in test clean-up. So if you
 *    need to add any that won't be deleted by the other users reseting, make sure to
 *    use a afterEach() or afterAll() block to explicitly delete it.
 */
export const getLogin = async () => {
  let retriesLeft = 3
  while (!realLogin && retriesLeft > 0) {
    try {
      realLogin = await generateRealLogin()
    } catch (err) {
      if (!(err instanceof LostRaceConditionToCreateRealUser)) throw err
      // we lost race condition to create the real user
      await sleep(2 + Math.random() * 4)
      retriesLeft -= 1
    }
  }
  return realLogin
}

export const generateRealLogin = async () => {
  const myUuid = generateRRUuid(callsites()[1])
  const email = generateEmail('real')
  const password = myUuid + '-1.Aa' // fulfill password requirements

  // try to sign the user in, and if that doesn't work, create the user
  let newUser = false
  let userId, IdToken, AccessToken
  try {
    // succeds if the user already exists
    ;({IdToken, AccessToken} = await userPoolClient
      .initiateAuth({AuthFlow: AuthFlow, AuthParameters: {USERNAME: username, PASSWORD: password}})
      .promise()
      .then(({AuthenticationResult}) => AuthenticationResult))
    userId = jwtDecode(IdToken)['cognito:username']
  } catch (err) {
    if (err.code !== 'NotAuthorizedException') throw err
    newUser = true

    // get an unathenticated ID from the identity pool, then
    // create user in the user pool, using the 'identity id' from the identity pool as the user pool 'username'
    ;({IdentityId: userId} = await identityPoolClient.getId().promise())
    try {
      await userPoolClient
        .signUp({
          Username: userId,
          Password: password,
          UserAttributes: [
            {Name: 'family_name', Value: familyName},
            {Name: 'email', Value: email},
          ],
          ClientMetadata: {autoConfirmUser: 'true'},
        })
        .promise()
    } catch (err) {
      if (err.code === 'UsernameExistsException') {
        // no way to delete the identity pool
        throw new LostRaceConditionToCreateRealUser()
      }
      throw err
    }

    // sign the user in
    ;({IdToken, AccessToken} = await userPoolClient
      .initiateAuth({AuthFlow: AuthFlow, AuthParameters: {USERNAME: userId, PASSWORD: password}})
      .promise()
      .then(({AuthenticationResult}) => AuthenticationResult))
  }

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
        .getCredentialsForIdentity({IdentityId: userId, Logins: {[userPoolLoginsKey]: IdToken}})
        .promise())
      break
    } catch (err) {
      if (err.code !== 'NotAuthorizedException') throw err
      console.warn(`Cognito identity pool rejected user '${userId}'s idToken '${IdToken}' with error: ${err}`)
    }
    retries -= 1
  }
  if (!creds) throw Error(`User '${userId}' failed to get credentials from cognito identity pool`)

  const client = await getAppSyncClient(creds)
  if (newUser) {
    const {errors} = await client.mutate({
      mutation: mutations.createCognitoOnlyUser,
      variables: {username},
      errorPolicy: 'all',
    })
    if (errors) {
      if (errors[0].errorType !== 'ClientError') throw new Error(errors[0].message)
      // we lost a race condition to claim the username or the email address
      // no way to delete identity pool entry, just user pool entry
      await userPoolClient.deleteUser({AccessToken}).promise()
      throw new LostRaceConditionToCreateRealUser()
    }
  }

  return {client, userId, password, email, username}
}
