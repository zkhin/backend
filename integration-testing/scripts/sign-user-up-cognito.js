#!/usr/bin/env node

const AWS = require('aws-sdk')
const dotenv = require('dotenv')
const prmt = require('prompt')
const pwdGenerator = require('generate-password')
const uuidv4 = require('uuid/v4')

dotenv.config()
const AWSPinpoint = new AWS.Pinpoint()

const awsRegion = process.env.AWS_REGION
if (awsRegion === undefined) throw new Error('Env var AWS_REGION must be defined')

const frontendCognitoClientId = process.env.COGNITO_FRONTEND_CLIENT_ID
if (frontendCognitoClientId === undefined) throw new Error('Env var COGNITO_FRONTEND_CLIENT_ID must be defined')

const testingCognitoClientId = process.env.COGNITO_TESTING_CLIENT_ID
if (testingCognitoClientId === undefined) throw new Error('Env var COGNITO_TESTING_CLIENT_ID must be defined')

const identityPoolId = process.env.COGNITO_IDENTITY_POOL_ID
if (identityPoolId === undefined) throw new Error('Env var COGNITO_IDENTITY_POOL_ID must be defined')

const pinpointAppId = process.env.PINPOINT_APPLICATION_ID
if (pinpointAppId === undefined) throw new Error('Env var PINPOINT_APPLICATION_ID must be defined')


// All users the test client creates must have this family name (or the sign up
// will be rejected). This is to make it easier to clean them out later.
const familyName = 'TESTER'

prmt.message = ''
prmt.start()

const prmtSchema = {
  properties: {
    email: {
      description: 'email?',
      pattern: /^\S+@\S+$/,
    },
    phone: {
      description: 'phone number? (ex: +14151231234)',
      pattern: /^\+[0-9]{5,15}$/,
    },
    password: {
      description: 'Password? leave blank to auto-generate',
      hidden: true,
    },
    autoconfirm: {
      description: 'Automatically confirm the user? Else a confirmation code will be sent to the provided email',
      default: 'true',
      message: 'Please enter "t" or "f"',
      type: 'boolean',
      required: true,
    },
    pinpointAnalytics: {
      description: 'Send analytics to pinpoint? A new endpoint ID will be automatically generated',
      default: 'true',
      message: 'Please enter "t" or "f"',
      type: 'boolean',
      required: true,
    },
  },
}

// Prompt and get user input then display those data in console.
console.log('Please enter email or phone, or both.')
prmt.get(prmtSchema, async (err, result) => {
  if (err) {
    console.log(err)
    return 1
  }
  if (! result.email && ! result.phone) throw 'At least one of email or phone is required'
  const pinpointEndpointId = result.pinpointAnalytics ? await generatePinpointEndpointId() : null
  await signUserUp(result.email, result.phone, result.password, result.autoconfirm, pinpointEndpointId)
})

const generatePinpointEndpointId = async () => {
  const endpointId = uuidv4()
  await AWSPinpoint.updateEndpoint({
    ApplicationId: pinpointAppId,
    EndpointId: endpointId,
    EndpointRequest: {},
  }).promise()
  console.log(`Auto-generated pinpoint endpoint id: ${endpointId}`)
  return endpointId
}

const signUserUp = async (email, phone, password, autoconfirm, pinpointEndpointId) => {
  if (! password) {
    password = pwdGenerator.generate({numbers: true, symbols: true, strict: true})
    console.log(`Auto-generated password: ${password}`)
  }
  const userAttrs = []
  if (autoconfirm) {
    userAttrs.push({
      Name: 'family_name',
      Value: familyName,
    })
  }
  if (email) {
    userAttrs.push({
      Name: 'email',
      Value: email,
    })
  }
  if (phone) {
    userAttrs.push({
      Name: 'phone_number',
      Value: phone,
    })
  }

  // get a new un-authenticated ID from the identity pool
  const identityPoolClient = new AWS.CognitoIdentity({params: {
    IdentityPoolId: identityPoolId,
  }})
  const idResp = await identityPoolClient.getId().promise()
  const userId = idResp['IdentityId']

  // create an entry in the user pool with matching 'cognito username'<->'identity id'
  const userPoolClientId = autoconfirm ? testingCognitoClientId : frontendCognitoClientId
  const userPoolClient = new AWS.CognitoIdentityServiceProvider({params: {
    ClientId: userPoolClientId,
    Region: awsRegion,
  }})
  const respSignUp = await userPoolClient.signUp({
    Username: userId,
    Password: password,
    UserAttributes: userAttrs,
    AnalyticsMetadata: {
      AnalyticsEndpointId: pinpointEndpointId,  // ignored if null
    },
  }).promise()

  if (pinpointEndpointId) {
    await AWSPinpoint.updateEndpoint({
      ApplicationId: pinpointAppId,
      EndpointId: pinpointEndpointId,
      EndpointRequest: {
        User: {
          UserId: userId
        },
      },
    }).promise()
  }

  console.log(respSignUp)
}
