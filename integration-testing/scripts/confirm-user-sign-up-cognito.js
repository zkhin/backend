#!/usr/bin/env node

const AWS = require('aws-sdk')
const dotenv = require('dotenv')
const moment = require('moment')
const prmt = require('prompt')
const rp = require('request-promise-native')
const util = require('util')

dotenv.config()

const api_key = process.env.REAL_AUTH_API_KEY
if (api_key === undefined) throw new Error('Env var REAL_AUTH_API_KEY must be defined')

const api_root = process.env.REAL_AUTH_API_ROOT
if (api_root === undefined) throw new Error('Env var REAL_AUTH_API_ROOT must be defined')

const pinpointAppId = process.env.PINPOINT_APPLICATION_ID


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
  let creds = await confirmUser(result.userId, result.confirmationCode, result.pinpointEndpointId)
  if (result.pinpointEndpointId) await trackWithPinpoint(result.pinpointEndpointId, result.userId, creds)
})

const confirmUser = async (userId, confirmationCode) => {
  // throws exception if code is incorrect
  let resp = await rp.post({
    uri: api_root + '/user/confirm',
    headers: {'x-api-key': api_key},
    json: true,
    qs: {userId, code: confirmationCode},
  })
  console.log('User confirmed.')
  return resp.credentials
}

const trackWithPinpoint = async (endpointId, userId, creds) => {
  if (pinpointAppId === undefined) throw new Error('Env var PINPOINT_APPLICATION_ID must be defined')
  const credentials = new AWS.Credentials(creds.AccessKeyId, creds.SecretKey, creds.SessionToken)
  const pinpoint = new AWS.Pinpoint({credentials, params: {ApplicationId: pinpointAppId}})

  // https://docs.aws.amazon.com/pinpoint/latest/developerguide/event-streams-data-app.html
  const eventType = '_userauth.sign_up'
  let resp = await pinpoint.putEvents({EventsRequest: {BatchItem: {[endpointId]: {
    Endpoint: {},
    Events: {[eventType]:{
      EventType: eventType,
      Timestamp: moment().toISOString(),
    }},
  }}}}).promise()
  if (resp.EventsResponse.Results[endpointId].EventsItemResponse[eventType].StatusCode == 202) {
    console.log(`Pinpoint event '${eventType}' recorded on for endpoint '${endpointId}'`)
  }
  else {
    console.log(`Error recording pinpoint event '${eventType}' recorded on for endpoint '${endpointId}'`)
    console.log(util.inspect(resp, {showHidden: false, depth: null}))
  }
}
