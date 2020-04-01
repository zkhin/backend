#!/usr/bin/env node

const AWS = require('aws-sdk')
const dotenv = require('dotenv')
const prmt = require('prompt')

dotenv.config()

const awsRegion = process.env.AWS_REGION
if (awsRegion === undefined) throw new Error('Env var AWS_REGION must be defined')

const frontendCognitoClientId = process.env.COGNITO_FRONTEND_CLIENT_ID
if (frontendCognitoClientId === undefined) throw new Error('Env var COGNITO_FRONTEND_CLIENT_ID must be defined')

prmt.message = ''
prmt.start()

const prmtSchema = {
  properties: {
    userId: {
      description: 'User id (aka cognito user pool \'username\') of user to confirm?',
    },
    confirmationCode: {
      description: 'Confirmation code from email/sms?',
      pattern: /^[0-9]{6}$/,
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
  await confirmUser(result.userId, result.confirmationCode, result.pinpointEndpointId)
})

const confirmUser = async (userId, confirmationCode, pinpointEndpointId) => {
  const userPoolClient = new AWS.CognitoIdentityServiceProvider({params: {
    ClientId: frontendCognitoClientId,
    Region: awsRegion,
    AnalyticsMetadata: { AnalyticsEndpointId: pinpointEndpointId },  // ignored if null
  }})

  // empty response upon success
  await userPoolClient.confirmSignUp({
    ConfirmationCode: confirmationCode,
    Username: userId,
  }).promise()

  console.log('User successfully confirmed.')
}
