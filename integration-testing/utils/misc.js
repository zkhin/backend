/* Misc utils functions for use in tests
 */

const fs = require('fs')
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


module.exports = {
  shortRandomString,
  sleep,
  uploadMedia,
}
