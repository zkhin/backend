#!/usr/bin/env node

const AWS = require('aws-sdk')
const dotenv = require('dotenv')
const prmt = require('prompt')
const pwdGenerator = require('generate-password')

dotenv.config()

const awsRegion = process.env.AWS_REGION
if (awsRegion === undefined) throw new Error('Env var AWS_REGION must be defined')

const testingCognitoClientId = process.env.COGNITO_TESTING_CLIENT_ID
if (testingCognitoClientId === undefined) throw new Error('Env var COGNITO_TESTING_CLIENT_ID must be defined')

prmt.message = ''
prmt.start()

const prmtSchema = {
  properties: {
    usernameLike: {
      description: 'Email, phone, username or user id?',
    },
    confirmationCode: {
      description: 'Confirmation code from email/sms?',
      pattern: /^[0-9]{6}$/,
    },
    password: {
      description: 'New password? leave blank to auto-generate',
      hidden: true,
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
  await chooseNewPassword(result.usernameLike, result.confirmationCode, result.password, result.pinpointEndpointId)
})

const chooseNewPassword = async (usernameLike, confirmationCode, password, pinpointEndpointId) => {
  if (! password) {
    password = pwdGenerator.generate({numbers: true, symbols: true, strict: true})
    console.log(`Auto generated password: ${password}`)
  }
  const userPoolClient = new AWS.CognitoIdentityServiceProvider({params: {
    ClientId: testingCognitoClientId,
    Region: awsRegion,
    AnalyticsMetadata: { AnalyticsEndpointId: pinpointEndpointId },  // ignored if null
  }})

  // empty response upon success
  await userPoolClient.confirmForgotPassword({
    ConfirmationCode: confirmationCode,
    Username: usernameLike,
    Password: password,
  }).promise()

  console.log('You may now use your new password to sign in')
}
