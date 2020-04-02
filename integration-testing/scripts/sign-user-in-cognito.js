#!/usr/bin/env node

const AWS = require('aws-sdk')
const dotenv = require('dotenv')
const fs = require('fs')
const jwtDecode = require('jwt-decode')
const moment = require('moment')
const prmt = require('prompt')
const util = require('util')

dotenv.config()

const cognitoClientId = process.env.COGNITO_TESTING_CLIENT_ID
if (cognitoClientId === undefined) throw new Error('Env var COGNITO_TESTING_CLIENT_ID must be defined')

const awsRegion = process.env.AWS_REGION
if (awsRegion === undefined) throw new Error('Env var AWS_REGION must be defined')

const identityPoolId = process.env.COGNITO_IDENTITY_POOL_ID
if (identityPoolId === undefined) throw new Error('Env var COGNITO_IDENTITY_POOL_ID must be defined')

const userPoolId = process.env.COGNITO_USER_POOL_ID
if (userPoolId === undefined) throw new Error('Env var COGNITO_USER_POOL_ID must be defined')

const accessKeyId = process.env.FRONTEND_IAM_USER_ACCESS_KEY_ID
const secretAccessKey = process.env.FRONTEND_IAM_USER_SECRET_ACCESS_KEY
const pinpointAppId = process.env.PINPOINT_APPLICATION_ID

const cognitoUserPoolClient = new AWS.CognitoIdentityServiceProvider({params: {
  ClientId: cognitoClientId,
  Region: awsRegion,
}})

const cognitoIndentityPoolClient = new AWS.CognitoIdentity({params: {
  IdentityPoolId: identityPoolId,
}})


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
      description: 'Pinpoint endpoint for analytics tracking? Leave blank to skip',
    },
  },
}

// Prompt and get user input then display those data in console.
prmt.get(prmtSchema, async (err, result) => {
  if (err) {
    console.log(err)
    return 1
  }
  const tokens = await generateTokens(result.username, result.password)
  if (result.pinpointEndpointId) trackWithPinpoint(result.pinpointEndpointId, tokens)
  if (tokens) {
    const gqlCreds = await generateGQLCredentials(tokens['IdToken'])
    const output = JSON.stringify({
      authProvider: 'COGNITO',
      tokens: tokens,
      credentials: gqlCreds,
    }, null, 2)
    if (result.destination) fs.writeFileSync(result.destination, output + '\n')
    else console.log(output)
  }
})

const generateTokens = async (username, password) => {
  // sign them in
  try {
    return await cognitoUserPoolClient.initiateAuth({
      AuthFlow: 'USER_PASSWORD_AUTH',
      AuthParameters: {USERNAME: username, PASSWORD: password},
    }).promise().then(resp => resp['AuthenticationResult'])
  }
  catch ( err ) {
    console.log(err)
    return null
  }
}

const generateGQLCredentials = async (idToken) => {
  const userId = jwtDecode(idToken)['cognito:username']
  const Logins = {[`cognito-idp.${awsRegion}.amazonaws.com/${userPoolId}`]: idToken}
  const resp = await cognitoIndentityPoolClient.getCredentialsForIdentity({IdentityId: userId, Logins}).promise()
  return resp['Credentials']
}

const trackWithPinpoint = async (endpointId, tokens) => {
  if (accessKeyId === undefined) throw new Error('Env var FRONTEND_IAM_USER_ACCESS_KEY_ID must be defined')
  if (secretAccessKey === undefined) throw new Error('Env var FRONTEND_IAM_USER_SECRET_ACCESS_KEY must be defined')
  if (pinpointAppId === undefined) throw new Error('Env var PINPOINT_APPLICATION_ID must be defined')
  const pinpoint = new AWS.Pinpoint({accessKeyId, secretAccessKey, params: {ApplicationId: pinpointAppId}})

  // https://docs.aws.amazon.com/pinpoint/latest/developerguide/event-streams-data-app.html
  const eventType = tokens ? '_userauth.sign_in' : '_userauth.auth_fail'
  let resp = await pinpoint.putEvents({EventsRequest: {BatchItem: {[endpointId]: {
    Endpoint: {},
    Events: {[eventType]:{
      EventType: eventType,
      Timestamp: moment().toISOString(),
    }},
  }}}}).promise()
  if (resp['EventsResponse']['Results'][endpointId]['EventsItemResponse'][eventType]['StatusCode'] == 202) {
    console.log(`Pinpoint event '${eventType}' recorded on for endpoint '${endpointId}'`)
  }
  else {
    console.log(`Error recording pinpoint event '${eventType}' recorded on for endpoint '${endpointId}'`)
    console.log(util.inspect(resp, {showHidden: false, depth: null}))
  }
}
