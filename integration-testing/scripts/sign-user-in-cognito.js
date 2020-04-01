#!/usr/bin/env node

const AWS = require('aws-sdk')
const dotenv = require('dotenv')
const fs = require('fs')
const jwtDecode = require('jwt-decode')
const prmt = require('prompt')

dotenv.config()

const cognitoClientId = process.env.COGNITO_TESTING_CLIENT_ID
if (cognitoClientId === undefined) throw new Error('Env var COGNITO_TESTING_CLIENT_ID must be defined')

const awsRegion = process.env.AWS_REGION
if (awsRegion === undefined) throw new Error('Env var AWS_REGION must be defined')

const identityPoolId = process.env.COGNITO_IDENTITY_POOL_ID
if (identityPoolId === undefined) throw new Error('Env var COGNITO_IDENTITY_POOL_ID must be defined')

const userPoolId = process.env.COGNITO_USER_POOL_ID
if (userPoolId === undefined) throw new Error('Env var COGNITO_USER_POOL_ID must be defined')

prmt.message = ''
prmt.start()

const prmtSchema = {
  properties: {
    username: {
      description: 'User\'s email, phone or human-readable username?',
      required: true,
    },
    password: {
      description: 'User\'s password?',
      required: true,
      hidden: true,
    },
    destination: {
      description: 'Filename to write the results to? leave blank for stdout',
    },
    pinpointEndpointId: {
      description: 'Pinpoint endpoint id to send analytics to? Leave blank to skip',
    },
  },
}

// Prompt and get user input then display those data in console.
prmt.get(prmtSchema, async (err, result) => {
  if (err) {
    console.log(err)
    return 1
  }
  const tokens = await generateTokens(result.username, result.password, result.pinpointEndpointId)
  const gqlCreds = await generateGQLCredentials(tokens['IdToken'])
  const output = JSON.stringify({
    authProvider: 'COGNITO',
    tokens: tokens,
    credentials: gqlCreds,
  }, null, 2)
  if (result.destination) fs.writeFileSync(result.destination, output + '\n')
  else console.log(output)
})

const generateTokens = async (username, password, pinpointEndpointId) => {
  // sign them in
  const cognitoUserPoolClient = new AWS.CognitoIdentityServiceProvider({params: {
    ClientId: cognitoClientId,
    Region: awsRegion,
    AnalyticsMetadata: { AnalyticsEndpointId: pinpointEndpointId },  // ignored if null
  }})
  const resp = await cognitoUserPoolClient.initiateAuth({
    AuthFlow: 'USER_PASSWORD_AUTH',
    AuthParameters: { USERNAME: username, PASSWORD: password },
  }).promise()
  return resp['AuthenticationResult']
}

const generateGQLCredentials = async (idToken) => {
  const cognitoIndentityPoolClient = new AWS.CognitoIdentity({params: {
    IdentityPoolId: identityPoolId,
  }})
  const userId = jwtDecode(idToken)['cognito:username']
  const Logins = {[`cognito-idp.${awsRegion}.amazonaws.com/${userPoolId}`]: idToken}
  const resp = await cognitoIndentityPoolClient.getCredentialsForIdentity({IdentityId: userId, Logins}).promise()
  return resp['Credentials']
}
