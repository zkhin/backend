#!/usr/bin/env node

const AWS = require('aws-sdk')
const AWSAppSyncClient = require('aws-appsync').default
const dotenv = require('dotenv')
const fs = require('fs')
const gql = require('graphql-tag')
const prmt = require('prompt')
const rp = require('request-promise-native')
const uuidv4 = require('uuid/v4')
require('isomorphic-fetch')

dotenv.config()

const cognitoClientId = process.env.COGNITO_TESTING_CLIENT_ID
if (cognitoClientId === undefined) throw new Error('Env var COGNITO_TESTING_CLIENT_ID must be defined')

const awsRegion = process.env.AWS_REGION
if (awsRegion === undefined) throw new Error('Env var AWS_REGION must be defined')

const identityPoolId = process.env.COGNITO_IDENTITY_POOL_ID
if (identityPoolId === undefined) throw new Error('Env var COGNITO_IDENTITY_POOL_ID must be defined')

const userPoolId = process.env.COGNITO_USER_POOL_ID
if (userPoolId === undefined) throw new Error('Env var COGNITO_USER_POOL_ID must be defined')

const appsyncApiUrl = process.env.APPSYNC_API_URL
if (appsyncApiUrl === undefined) throw new Error('Env var APPSYNC_API_URL must be defined')


const cognitoUserPoolClient = new AWS.CognitoIdentityServiceProvider({params: {
  ClientId: cognitoClientId,
  Region: awsRegion,
}})

const cognitoIndentityPoolClient = new AWS.CognitoIdentity({params: {
  IdentityPoolId: identityPoolId,
}})


prmt.message = ''
prmt.start()

const facebookHelp = `To generate:
  - create a facebook developer account if needed, get it associated with our facebook app
  - navigate to https://developers.facebook.com/tools/explorer/
  - select our app in the top-right corner
  - copy-paste the access token
`

const googleHelp = `To generate:
  - navigate to https://developers.google.com/oauthplayground/
  - click the settings gear in the top-right corner
  - select 'Use your own OAuth credentials'
  - enter our OAuth Client ID & secret from the web application listed here:
    https://console.developers.google.com/apis/credentials?project=selfly---dev-1566405434462
  - in the box on the bottom left, where it says 'Input your own scopes', enter 'email'
  - click 'Authorize APIs'
  - go through the authentication flow until you're back to the playground
  - click 'Exchange authorization code for tokens'
  - in the response json on the right, copy-paste the **id** token
`

const prmtSchema = {
  properties: {
    authSource: {
      description: 'Where is the user from? Enter `c` for Cognito, `f` for Facebook, or `g` for Google.',
      required: true,
      pattern: /^[cfg]?$/,
    },
    username: {
      description: 'User\'s email, phone or human-readable username?',
      required: true,
      ask: () => prmt.history('authSource').value == 'c',
    },
    password: {
      description: 'User\'s password?',
      required: true,
      hidden: true,
      ask: () => prmt.history('authSource').value == 'c',
    },
    facebookAccessToken: {
      description: `A facebook access token for our app for the User? ${facebookHelp}?`,
      required: true,
      ask: () => prmt.history('authSource').value == 'f',
    },
    googleIdToken: {
      description: `A google **id** (not access) token for the User? ${googleHelp}?`,
      required: true,
      ask: () => prmt.history('authSource').value == 'g',
    },
    path: {
      description: 'Path to image file to upload? Ex: `./image.jpeg` ',
      required: true,
    },
    caption: {
      description: 'Optional caption for the post?',
      required: false,
    },
  },
}


// Effectively the main() function
prmt.get(prmtSchema, async (err, result) => {
  if (err) {
    console.log(err)
    return 1
  }

  const token = await (async () => {
    if (result.authSource == 'c') {
      process.stdout.write('Signing cognito user in...')
      const tokens = await generateCognitoTokens(result.username, result.password)
      process.stdout.write(' done.\n')
      return tokens['IdToken']
    }
    if (result.authSource == 'f') return result.facebookAccessToken
    if (result.authSource == 'g') return result.googleIdToken
    throw `Unrecognized auth source '${result.authSource}'`
  })()

  process.stdout.write('Exchanging auth token for graphql-authorized JWT token...')
  const creds = await generateGQLCredentials(result.authSource, token)
  const awsCredentials = new AWS.Credentials(creds['AccessKeyId'], creds['SecretKey'], creds['SessionToken'])
  const appsyncClient = new AWSAppSyncClient({
    url: appsyncApiUrl,
    region: awsRegion,
    auth: {
      type: 'AWS_IAM',
      credentials: awsCredentials,
    },
    disableOffline: true,
  }, {
    defaultOptions: {
      query: {
        fetchPolicy: 'network-only',
        errorPolicy: 'all',
      },
    },
  })
  process.stdout.write(' done.\n')

  process.stdout.write('Reading image from disk...')
  const obj = fs.readFileSync(result.path)
  process.stdout.write(' done.\n')

  process.stdout.write('Adding pending post...')
  const postId = uuidv4()
  const variables = {postId, mediaId: uuidv4(), text: result.caption}
  let resp = await appsyncClient.mutate({ mutation: addOneImagePost, variables})
  const uploadUrl = resp['data']['addPost']['mediaObjects'][0]['uploadUrl']
  process.stdout.write(' done.\n')

  process.stdout.write('Uploading media...')
  await uploadMedia(obj, uploadUrl)
  process.stdout.write(' done.\n')

  process.stdout.write('Waiting for thumbnails to be generated...')
  while (true) {
    resp = await appsyncClient.query({ query: getPost, variables: {postId}})
    if (resp['data']['post']['postStatus'] != 'PENDING') break
    await new Promise(resolve => setTimeout(resolve, 1000))  // sleep one second
    process.stdout.write('.')
  }
  process.stdout.write(' done.\n')

  if (resp['data']['post']['postStatus'] == 'ERROR') {
    process.stdout.write('Error processing upload. Invalid jpeg?\n')
  }
  else {
    const media = resp['data']['post']['mediaObjects'][0]
    process.stdout.write('Post successfully added. Image urls:\n')
    process.stdout.write(`  native: ${media['url']}\n`)
    process.stdout.write(`  4k: ${media['url4k']}\n`)
    process.stdout.write(`  1080p: ${media['url1080p']}\n`)
    process.stdout.write(`  480p: ${media['url480p']}\n`)
  }
})


const addOneImagePost = gql(`mutation AddMediaPost ($postId: ID!, $mediaId: ID!, $text: String) {
  addPost (postId: $postId, text: $text, mediaObjectUploads: [{mediaId: $mediaId, mediaType: IMAGE}]) {
    postId
    postStatus
    mediaObjects {
      mediaId
      uploadUrl
    }
  }
}`)


const getPost = gql(`query GetPost ($postId: ID!) {
  post (postId: $postId) {
    postId
    postStatus
    text
    mediaObjects {
      mediaId
      mediaStatus
      url
      url480p
      url1080p
      url4k
    }
  }
}`)


const uploadMedia = async (obj, url) => {
  const options = {
    method: 'PUT',
    url: url,
    headers: {'Content-Type': 'image/jpeg'},
    body: obj,
  }
  return rp.put(options)
}


const generateCognitoTokens = async (username, password) => {
  // sign them in
  const resp = await cognitoUserPoolClient.initiateAuth({
    AuthFlow: 'USER_PASSWORD_AUTH',
    AuthParameters: {USERNAME: username, PASSWORD: password},
  }).promise()
  return resp['AuthenticationResult']
}


const generateGQLCredentials = async (authSource, token) => {
  const loginsKey = (() => {
    if (authSource == 'c') return `cognito-idp.${awsRegion}.amazonaws.com/${userPoolId}`
    if (authSource == 'f') return 'graph.facebook.com'
    if (authSource == 'g') return 'accounts.google.com'
    throw `Unrecognized auth source '${authSource}'`
  })()
  const Logins = {[loginsKey]: token}

  // add the user to the identity pool
  const idResp = await cognitoIndentityPoolClient.getId({Logins}).promise()
  const userId = idResp['IdentityId']

  // get credentials for appsync from the identity pool
  const resp = await cognitoIndentityPoolClient.getCredentialsForIdentity({IdentityId: userId, Logins}).promise()
  return resp['Credentials']
}
