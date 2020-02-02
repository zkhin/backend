/* Misc utils functions for use in tests */

const jpeg = require('jpeg-js')
const gql = require('graphql-tag')
const rp = require('request-promise-native')

const shortRandomString = () => Math.random().toString(36).substring(7)

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms))

const uploadMedia = async (data, contentType, url) => {
  const options = {
    method: 'PUT',
    url: url,
    headers: {'Content-Type': contentType},
    body: data,
  }
  return rp.put(options)
}

const generateRandomJpeg = (width, height) => {
  const buf = Buffer.alloc(width * height * 4)
  let i = 0
  while (i < buf.length) {
    buf[i++] = Math.floor(Math.random() * 256)
  }
  const imgData = {
    data: buf,
    width: width,
    height: height
  }
  const quality = 50
  return jpeg.encode(imgData, quality).data
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
    await sleep(pollingIntervalMs)
    waitedMs += pollingIntervalMs
  }
  throw Error(`Post ${postId} never reached status COMPLETED`)
}

module.exports = {
  generateRandomJpeg,
  uploadMedia,
  shortRandomString,
  sleep,
  sleepUntilPostCompleted,
}
