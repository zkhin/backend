#!/usr/bin/env node

const AWS = require('aws-sdk')
const dotenv = require('dotenv')
const uuidv4 = require('uuid/v4')

dotenv.config()

const accessKeyId = process.env.FRONTEND_IAM_USER_ACCESS_KEY_ID
if (accessKeyId === undefined) throw new Error('Env var FRONTEND_IAM_USER_ACCESS_KEY_ID must be defined')

const secretAccessKey = process.env.FRONTEND_IAM_USER_SECRET_ACCESS_KEY
if (secretAccessKey === undefined) throw new Error('Env var FRONTEND_IAM_USER_SECRET_ACCESS_KEY must be defined')

const pinpointAppId = process.env.PINPOINT_APPLICATION_ID
if (pinpointAppId === undefined) throw new Error('Env var PINPOINT_APPLICATION_ID must be defined')


const main = async () => {
  const pinpoint = new AWS.Pinpoint({accessKeyId, secretAccessKey})
  const endpointId = uuidv4()
  await pinpoint.updateEndpoint({
    ApplicationId: pinpointAppId,
    EndpointId: endpointId,
    EndpointRequest: {},
  }).promise()
  console.log(`New pinpoint endpoint '${endpointId}' generated`)
}

main()
