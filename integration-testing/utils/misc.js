/* Misc utils functions for use in tests */

const fs = require('fs')
const gql = require('graphql-tag')
const rp = require('request-promise-native')


const shortRandomString = () => Math.random().toString(36).substring(7)

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms))

const uploadMedia = async (filename, contentType, url) => {
  const obj = fs.readFileSync(filename)
  const options = {
    method: 'PUT',
    url: url,
    headers: {'Content-Type': contentType},
    body: obj,
  }
  return rp.put(options)
}

// would be nice to query the media object directly but theres currently
// no graphql query field to do so
const sleepUntilPostCompleted = async (gqlClient, postId) => {
  const pollingIntervalMs = 1000
  const maxWaitMs = 10000
  const queryPost = gql(`query Post ($postId: ID!) {
    post (postId: $postId) {
      postId
      postStatus
    }
  }`)

  let waitedMs = 0
  while (waitedMs < maxWaitMs) {
    let resp = await gqlClient.query({query: queryPost, variables: {postId}})
    if (resp['data']['post']['postStatus'] == 'COMPLETED') return
    sleep(pollingIntervalMs)
    waitedMs += pollingIntervalMs
  }
  throw Error(`Post ${postId} never reached status COMPLETED`)
}

module.exports = {
  uploadMedia,
  shortRandomString,
  sleep,
  sleepUntilPostCompleted,
}
